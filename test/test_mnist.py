from functools import partial
from pathlib import Path
import requests
from time import sleep
from tqdm import tqdm
import torch
import torch.utils.tensorboard
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
import datastream

import lantern


def test_mnist():
    torch.set_grad_enabled(False)

    urls = {
        "t10k-labels-idx1-ubyte.gz": "https://storage.googleapis.com/cvdf-datasets/mnist/t10k-labels-idx1-ubyte.gz",
        "t10k-images-idx3-ubyte.gz": "https://storage.googleapis.com/cvdf-datasets/mnist/t10k-images-idx3-ubyte.gz",
        "train-labels-idx1-ubyte.gz": "https://storage.googleapis.com/cvdf-datasets/mnist/train-labels-idx1-ubyte.gz",
        "train-images-idx3-ubyte.gz": "https://storage.googleapis.com/cvdf-datasets/mnist/train-images-idx3-ubyte.gz",
    }
    raw = Path("data/MNIST/raw")
    raw.mkdir(exist_ok=True, parents=True)
    for name, url in urls.items():
        request = requests.get(url, allow_redirects=True)
        (raw / name).write_bytes(request.content)

    transform = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
    )

    train_dataset = datastream.Dataset.from_subscriptable(
        datasets.MNIST("data", train=True, transform=transform, download=True)
    )
    early_stopping_dataset = datastream.Dataset.from_subscriptable(
        datasets.MNIST("data", train=False, transform=transform, download=True)
    )

    train_data_loader = (
        datastream.Datastream(train_dataset).take(16 * 4).data_loader(batch_size=16)
    )
    early_stopping_data_loader = (
        datastream.Datastream(early_stopping_dataset)
        .take(16 * 4)
        .data_loader(batch_size=16)
    )
    evaluate_data_loaders = dict(
        evaluate_train=train_data_loader,
        evaluate_early_stopping=early_stopping_data_loader,
    )

    device = torch.device("cpu")
    model = nn.Sequential(
        nn.Conv2d(1, 4, 3, 1),
        lantern.Lambda(partial(F.max_pool2d, kernel_size=2)),
        lantern.Lambda(partial(torch.flatten, start_dim=1)),
        lantern.Lambda(F.relu),
        nn.Linear(676, 10),
        lantern.Lambda(partial(F.log_softmax, dim=1)),
    ).to(device)

    optimizer = optim.Adadelta(model.parameters(), lr=5e-3)

    tensorboard_logger = torch.utils.tensorboard.SummaryWriter()
    early_stopping = lantern.EarlyStopping(tensorboard_logger=tensorboard_logger)
    train_metrics = dict(
        loss=lantern.Metric().reduce(lambda state, loss: loss.item()),
    )

    for epoch in lantern.Epochs(2):

        for examples, targets in lantern.ProgressBar(
            train_data_loader, "train", train_metrics
        ):
            with lantern.module_train(model), torch.enable_grad():
                predictions = model(examples)
                loss = F.nll_loss(predictions, targets)
                loss.backward()
            optimizer.step()
            optimizer.zero_grad()

            train_metrics["loss"].update_(loss)
            sleep(0.5)

            for metric_name, metric in train_metrics.items():
                metric.log(tensorboard_logger, "train", metric_name, epoch)

        print(lantern.MetricTable("train", train_metrics))

        evaluate_metrics = {
            name: dict(
                loss=lantern.Metric().reduce(
                    lambda state, loss: dict(loss=loss.item())
                ),
            )
            for name in evaluate_data_loaders
        }

        for name, data_loader in evaluate_data_loaders.items():
            for examples, targets in tqdm(data_loader, desc=name, leave=False):
                with lantern.module_eval(model):
                    predictions = model(examples)
                    loss = F.nll_loss(predictions, targets)

                evaluate_metrics[name]["loss"].update_(loss)

            for metrics in evaluate_metrics[name].values():
                metrics.log_dict(tensorboard_logger, name, epoch)

            print(lantern.MetricTable(name, evaluate_metrics[name]))

        early_stopping = early_stopping.score(
            -evaluate_metrics["evaluate_early_stopping"]["loss"].compute()["loss"]
        )
        if early_stopping.scores_since_improvement == 0:
            torch.save(model.state_dict(), "model.pt")
            torch.save(optimizer.state_dict(), "optimizer.pt")
        elif early_stopping.scores_since_improvement > 5:
            break
        early_stopping.log(epoch).print()


if __name__ == "__main__":
    test_mnist()
