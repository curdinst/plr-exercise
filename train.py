from __future__ import print_function
import argparse
import torch
import wandb
import optuna
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import StepLR
from plr_exercise.models.cnn import Net

wandb.login()
artifact = wandb.Artifact(name="train.py", type="code")
artifact.add_file("/home/curdin/plr/plr-exercise/train.py")
# artifact.add_file(local_path=os.path.dirname(os.path.abspath(__file__))+"/train.py", name="train.py")
run = wandb.init(project="plr-exercise", job_type="train")
run.use_artifact(artifact)
run.log_artifact(artifact)


def train(args, model, device, train_loader, optimizer, epoch):
    """
    Train the model on the training dataset.

    Args:
        args (argparse.Namespace): Command-line arguments.
        model (torch.nn.Module): The model to be trained.
        device (torch.device): The device to run the training on (CPU or GPU).
        train_loader (torch.utils.data.DataLoader): DataLoader for the training dataset.
        optimizer (torch.optim.Optimizer): The optimizer used for training.
        epoch (int): The current epoch number.

    Returns:
        None
    """
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):

        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            wandb.log({"train_loss": loss.item()})
            print(
                "Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}".format(
                    epoch,
                    batch_idx * len(data),
                    len(train_loader.dataset),
                    100.0 * batch_idx / len(train_loader),
                    loss.item(),
                )
            )
            if args.dry_run:
                break


def test(model, device, test_loader, epoch):
    """
    Evaluate the model on the test dataset.

    Args:
        model (torch.nn.Module): The model to be evaluated.
        device (torch.device): The device to run the evaluation on (CPU or GPU).
        test_loader (torch.utils.data.DataLoader): DataLoader for the test dataset.
        epoch (int): The current epoch number.

    Returns:
        float: The average test loss.
    """
    model.eval()
    test_loss = 0
    correct = 0

    with torch.no_grad():
        for data, target in test_loader:

            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction="sum").item()  # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)
    wandb.log({"test_loss": test_loss})
    print(
        "\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n".format(
            test_loss, correct, len(test_loader.dataset), 100.0 * correct / len(test_loader.dataset)
        )
    )
    return test_loss


def main():
    """
    Main function to train the model on the MNIST dataset.
    """
    # Training settings
    parser = argparse.ArgumentParser(description="PyTorch MNIST Example")
    parser.add_argument(
        "--batch-size", type=int, default=64, metavar="N", help="input batch size for training (default: 64)"
    )
    parser.add_argument(
        "--test-batch-size", type=int, default=1000, metavar="N", help="input batch size for testing (default: 1000)"
    )
    parser.add_argument("--epochs", type=int, default=2, metavar="N", help="number of epochs to train (default: 14)")
    parser.add_argument("--lr", type=float, default=1.0, metavar="LR", help="learning rate (default: 1.0)")
    parser.add_argument("--gamma", type=float, default=0.7, metavar="M", help="Learning rate step gamma (default: 0.7)")
    parser.add_argument("--no-cuda", action="store_true", default=False, help="disables CUDA training")
    parser.add_argument("--dry-run", action="store_true", default=False, help="quickly check a single pass")
    parser.add_argument("--seed", type=int, default=1, metavar="S", help="random seed (default: 1)")
    parser.add_argument(
        "--log-interval",
        type=int,
        default=10,
        metavar="N",
        help="how many batches to wait before logging training status",
    )
    parser.add_argument("--save-model", action="store_true", default=False, help="For Saving the current Model")
    args = parser.parse_args()
    use_cuda = not args.no_cuda and torch.cuda.is_available()

    torch.manual_seed(args.seed)

    if use_cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    train_kwargs = {"batch_size": args.batch_size}
    test_kwargs = {"batch_size": args.test_batch_size}
    if use_cuda:
        cuda_kwargs = {"num_workers": 1, "pin_memory": True, "shuffle": True}
        train_kwargs.update(cuda_kwargs)
        test_kwargs.update(cuda_kwargs)

    transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])
    dataset1 = datasets.MNIST("../data", train=True, download=True, transform=transform)
    dataset2 = datasets.MNIST("../data", train=False, transform=transform)
    train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)
    test_loader = torch.utils.data.DataLoader(dataset2, **test_kwargs)
    study = optuna.create_study(study_name="plr-exercise", storage="sqlite:///plr_exercise.db", load_if_exists=True)

    def objective(trial):
        """
        Objective function for Optuna hyperparameter optimization.

        Args:
            trial (optuna.Trial): The current trial.

        Returns:
            float: The test loss.
        """
        lr = trial.suggest_loguniform("lr", 1e-5, 1e-1)
        epochs = trial.suggest_int("epochs", 1, 20)

        model = Net().to(device)
        optimizer = optim.Adam(model.parameters(), lr=lr)
        scheduler = StepLR(optimizer, step_size=1, gamma=args.gamma)

        for epoch in range(1, epochs + 1):
            train(args, model, device, train_loader, optimizer, epoch)
            test_loss = test(model, device, test_loader, epoch)
            scheduler.step()

        return test_loss

    study.optimize(objective, n_trials=100, timeout=600)
    study.best_params

    # model = Net().to(device)
    # optimizer = optim.Adam(model.parameters(), lr=args.lr)

    # scheduler = StepLR(optimizer, step_size=1, gamma=args.gamma)
    # for epoch in range(args.epochs):
    #     train(args, model, device, train_loader, optimizer, epoch)
    #     test(model, device, test_loader, epoch)
    #     scheduler.step()

    wandb.finish()


if __name__ == "__main__":
    main()
