import os
import time
from os.path import join

import numpy as np
from nltk.util import ngrams

from stepcovnet.common.utils import get_arrow_one_hot_encoder
from stepcovnet.common.utils import get_filename
from stepcovnet.common.utils import get_filenames_from_folder
from stepcovnet.common.utils import write_file


def get_binary_rep(arrow_values):
    return ((np.asarray(arrow_values).astype(int)[:, None] & (1 << np.arange(4))) > 0).astype(int)


def get_extended_binary_rep(arrow_combs):
    extended_binary_rep = []
    for i, arrow_comb in enumerate(arrow_combs):
        binary_rep = np.zeros((4, 4))
        for j, num in enumerate(list(arrow_comb)):
            binary_rep[int(num), j] = 1
        extended_binary_rep.append(binary_rep.ravel())
    return np.asarray(extended_binary_rep)


def create_tokens(timings):
    timings = timings.astype("float32")
    tokens = np.zeros((timings.shape[0], 3))
    tokens[0][0] = 1  # set start token
    next_note_token = np.append(timings[1:] - timings[:-1], np.asarray([0]))
    prev_note_token = np.append(np.asarray([0]), next_note_token[: -1])
    tokens[:, 1] = prev_note_token.reshape(1, -1)
    tokens[:, 2] = next_note_token.reshape(1, -1)
    return tokens.astype("float32")


def get_notes_ngram(binary_notes, lookback):
    padding = np.zeros((lookback, binary_notes.shape[1]))
    data_w_padding = np.append(padding, binary_notes, axis=0)
    return np.asarray(list(ngrams(data_w_padding, lookback)))


def get_arrows(timings, model, encoder):
    pred_notes = []
    lookback = model.layers[0].input_shape[0][1]
    classes = model.layers[-1].output_shape[1]
    tokens = np.expand_dims(np.expand_dims(create_tokens(timings), axis=1), axis=1)
    notes_ngram = np.expand_dims(get_notes_ngram(np.zeros((1, 16)), lookback)[-1], axis=0)
    for i, token in enumerate(tokens):
        pred = model.predict([notes_ngram, token])
        pred_arrow = np.random.choice(classes, 1, p=pred[0])[0]
        binary_rep = encoder.categories_[0][pred_arrow]
        pred_notes.append(binary_rep)
        binary_note = get_extended_binary_rep([binary_rep])
        notes_ngram = np.roll(notes_ngram, -1, axis=0)
        notes_ngram[0][-1] = binary_note
    return pred_notes


def generate_arrows(input_path, output_path, model, encoder, verbose, timing_name):
    song_name = get_filename(timing_name, False)
    with open(input_path + timing_name, "r") as timings_file:
        timings = np.asarray([line.replace("\n", "") for line in timings_file.readlines()]).astype("float32")

    if verbose:
        print("Generating arrows for " + song_name)

    arrows = get_arrows(timings, model, encoder)

    output_path = join(output_path, song_name + ".arrows")
    output_arrows = '\n'.join([str(arrow) for arrow in arrows])

    write_file(output_path=output_path, output_data=output_arrows)


def run_process(input_path, output_path, model, encoder, verbose):
    if os.path.isfile(input_path):
        generate_arrows(os.path.dirname(input_path), output_path, model, encoder, verbose, get_filename(input_path))
    else:
        timings_names = get_filenames_from_folder(input_path)
        for timing_name in timings_names:
            generate_arrows(input_path, output_path, model, encoder, verbose, timing_name)


def arrow_prediction(input_path,
                     output_path,
                     model_path,
                     verbose_int=0):
    start_time = time.time()
    if verbose_int not in [0, 1]:
        raise ValueError('%s is not a valid verbose input. Choose 0 for none or 1 for full' % verbose_int)
    verbose = True if verbose_int == 1 else False

    if not os.path.isdir(output_path):
        print('Output path not found. Creating directory...')
        os.makedirs(output_path, exist_ok=True)

    if not os.path.isfile(model_path):
        raise FileNotFoundError('Model %s is not found' % model_path)

    if os.path.isdir(input_path) or os.path.isfile(input_path):
        if verbose:
            print("Starting arrows prediction\n-----------------------------------------")
        from tensorflow.keras.models import load_model
        model = load_model(join(model_path), compile=False)
        encoder = get_arrow_one_hot_encoder()
        run_process(input_path, output_path, model, encoder, verbose)
    else:
        raise FileNotFoundError('Timing files path %s not found' % input_path)

    end_time = time.time()
    if verbose:
        print("Elapsed time was %g seconds\n" % (end_time - start_time))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Generate arrow types from .wav files")
    parser.add_argument("-i", "--input",
                        type=str,
                        help="Input timings path")
    parser.add_argument("-o", "--output",
                        type=str,
                        help="Output generated arrows path")
    parser.add_argument("--model",
                        type=str,
                        default="stepcovnet/models/retrained_arrow_model.h5",
                        help="Input trained model path")
    parser.add_argument("-v", "--verbose",
                        type=int,
                        default=0,
                        choices=[0, 1],
                        help="Verbosity: 0 - none, 1 - full")
    args = parser.parse_args()

    arrow_prediction(args.input,
                     args.output,
                     args.model,
                     args.verbose)
