from abc import ABC
from typing import Type

import numpy as np
from sklearn import preprocessing
from sklearn.model_selection import train_test_split

from stepcovnet import dataset, training, constants, utils


class AbstractConfig(ABC):
    def __init__(
        self, dataset_config: dict, lookback: int, difficulty: str, *args, **kwargs
    ):
        self.dataset_config = dataset_config
        self.lookback = lookback
        self.difficulty = difficulty

    @property
    def arrow_input_shape(self) -> tuple[None,]:
        return (None,)

    @property
    def arrow_mask_shape(self) -> tuple[None,]:
        return (None,)

    @property
    def audio_input_shape(self) -> tuple[int, int, int, int]:
        return (
            self.lookback,
            self.dataset_config["NUM_TIME_BANDS"],
            self.dataset_config["NUM_FREQ_BANDS"],
            1,
        )

    @property
    def label_shape(self) -> tuple[int,]:
        return (constants.NUM_ARROW_COMBS,)


class InferenceConfig(AbstractConfig):
    def __init__(
        self,
        audio_path: str,
        file_name: str,
        dataset_config: dict,
        lookback: int,
        difficulty: str,
        scalers: list[preprocessing.StandardScaler] | None = None,
    ):
        super(InferenceConfig, self).__init__(
            dataset_config=dataset_config, lookback=lookback, difficulty=difficulty
        )
        self.audio_path = audio_path
        self.file_name = file_name
        self.scalers = scalers


class TrainingConfig(AbstractConfig):
    def __init__(
        self,
        dataset_path: str,
        dataset_type: Type[dataset.ModelDataset],
        dataset_config: dict,
        hyperparameters: training.TrainingHyperparameters,
        all_scalers: list[preprocessing.StandardScaler] | None = None,
        limit: int = -1,
        lookback: int = 1,
        difficulty: str = "challenge",
        tokenizer_name: str = None,
    ):
        super(TrainingConfig, self).__init__(
            dataset_config=dataset_config, lookback=lookback, difficulty=difficulty
        )
        self.dataset_path = dataset_path
        self.dataset_type = dataset_type
        self.hyperparameters = hyperparameters
        self.all_scalers = all_scalers
        self.limit = limit
        self.tokenizer_name = tokenizer_name

        # Combine some of these to reduce the number of loops and save I/O reads
        (
            self.all_indexes,
            self.train_indexes,
            self.val_indexes,
        ) = self.get_train_val_split()
        self.num_samples = self.get_num_samples(self.all_indexes)
        self.num_train_samples = self.get_num_samples(self.train_indexes)
        self.num_val_samples = self.get_num_samples(self.val_indexes)
        # Disabling class weights since model currently performs better when disabled.
        self.train_class_weights = None  # self.get_class_weights(self.train_indexes)
        self.all_class_weights = None  # self.get_class_weights(self.all_indexes)
        self.init_bias_correction = self.get_init_bias_correction()
        self.train_scalers = self.get_train_scalers()

    def get_train_val_split(
        self,
    ) -> tuple[np.ndarray[int], np.ndarray[int], np.ndarray[int]]:
        all_indexes = []
        with self.enter_dataset as model_dataset:
            total_samples = 0
            index = 0
            for song_start_index, song_end_index in model_dataset.song_index_ranges:
                if not any(model_dataset.labels[song_start_index:song_end_index] < 0):
                    all_indexes.append(index)
                    total_samples += song_end_index - song_start_index
                    if 0 < self.limit < total_samples:
                        break
                index += 1
        all_indexes = np.array(all_indexes)
        train_indexes, val_indexes, _, _ = train_test_split(
            all_indexes, all_indexes, test_size=0.1, shuffle=True, random_state=42
        )
        return all_indexes, train_indexes, val_indexes

    def get_class_weights(self, indexes: np.ndarray[int]) -> dict:
        labels = None
        with self.enter_dataset as model_dataset:
            for index in indexes:
                song_start_index, song_end_index = model_dataset.song_index_ranges[
                    index
                ]
                encoded_arrows = model_dataset.onehot_encoded_arrows[
                    song_start_index:song_end_index
                ]
                if labels is None:
                    labels = encoded_arrows
                else:
                    labels = np.concatenate((labels, encoded_arrows), axis=0)

        class_counts = [
            labels[:, class_index].sum() for class_index in range(labels.shape[1])
        ]

        class_weights = dict(
            zip(
                list(range(len(class_counts))),
                list(
                    0
                    if class_count == 0
                    else (len(labels) / class_count) / len(class_counts)
                    for class_count in class_counts
                ),
            )
        )

        return dict(enumerate(class_weights))

    def get_init_bias_correction(self) -> float:
        # Best practices mentioned in
        # https://www.tensorflow.org/tutorials/structured_data/imbalanced_data#optional_set_the_correct_initial_bias
        # Not completely correct but works for now
        num_all = self.num_train_samples
        num_pos = 0
        with self.enter_dataset as model_dataset:
            for index in self.train_indexes:
                song_start_index, song_end_index = model_dataset.song_index_ranges[
                    index
                ]
                num_pos += model_dataset.labels[song_start_index:song_end_index].sum()
        num_neg = num_all - num_pos
        return np.log(num_pos / num_neg)

    def get_train_scalers(self) -> list | None:
        training_scalers = None
        with self.enter_dataset as model_dataset:
            for index in self.train_indexes:
                song_start_index, song_end_index = model_dataset.song_index_ranges[
                    index
                ]
                features = model_dataset.features[song_start_index:song_end_index]
                training_scalers = utils.get_channel_scalers(
                    features, existing_scalers=training_scalers
                )
        return training_scalers

    def get_num_samples(self, indexes: np.ndarray[int]) -> int:
        num_all = 0
        with self.enter_dataset as model_dataset:
            for index in indexes:
                song_start_index, song_end_index = model_dataset.song_index_ranges[
                    index
                ]
                num_all += song_end_index - song_start_index
        return num_all

    @property
    def enter_dataset(self) -> dataset.ModelDataset:
        return self.dataset_type(
            self.dataset_path, difficulty=self.difficulty
        ).__enter__()
