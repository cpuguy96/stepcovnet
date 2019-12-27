from common.utilFunctions import get_filenames_from_folder, get_filename, standardize_filename
from wrapper.wav_converter import wav_converter
from wrapper.arrow_prediction import arrow_prediction
from wrapper.timing_arrow_combiner import timing_arrow_combiner
from wrapper.timing_prediction import timing_prediction

from shutil import copyfile, rmtree
from os.path import join

import os
import warnings
import time

warnings.filterwarnings("ignore")


def __copy_to_tmp_folder(input_path, tmp_folder_name, batch):
    if batch:
        for input_audio_name in get_filenames_from_folder(input_path):
            new_file_name = standardize_filename(get_filename(input_audio_name, False))
            copyfile(join(input_path, input_audio_name), join(tmp_folder_name, "input", new_file_name))
    else:
        new_file_name = standardize_filename(get_filename(input_path, False))
        copyfile(join(input_path), join(tmp_folder_name, "input", new_file_name))


def __build_tmp_folder(tmp_folder_name):
    rmtree(tmp_folder_name, ignore_errors=True)
    os.makedirs(join(tmp_folder_name), exist_ok=True)
    os.makedirs(join(tmp_folder_name, "input"), exist_ok=True)
    os.makedirs(join(tmp_folder_name, "wav"), exist_ok=True)
    os.makedirs(join(tmp_folder_name, "timing"), exist_ok=True)
    os.makedirs(join(tmp_folder_name, "arrows"), exist_ok=True)


def __generate_notes(output_path,
                     tmp_folder_name,
                     timing_model,
                     arrow_model,
                     scalers_path,
                     verbose_int):

    wav_converter(input_path=join(tmp_folder_name, "input/"),
                  output_path=join(tmp_folder_name, "wav"),
                  verbose_int=verbose_int)

    timing_prediction(input_path=join(tmp_folder_name, "wav/"),
                      output_path=join(tmp_folder_name, "timing"),
                      model_path=join(timing_model),
                      scaler_path=join(scalers_path),
                      verbose_int=verbose_int)

    # generate arrows for wav
    arrow_prediction(input_path=join(tmp_folder_name, "timing/"),
                     output_path=join(tmp_folder_name, "arrows"),
                     model_path=join(arrow_model),
                     verbose_int=verbose_int)

    # combine timings and arrows
    timing_arrow_combiner(wavs_path=join(tmp_folder_name, "wav/"),
                          timings_path=join(tmp_folder_name, "timing/"),
                          arrows_path=join(tmp_folder_name, "arrows/"),
                          output_path=join(output_path),
                          verbose_int=verbose_int)


def stepmania_note_generator(input_path,
                             output_path,
                             scalers_path,
                             timing_model,
                             arrow_model,
                             verbose_int=0):
    start_time = time.time()
    if verbose_int not in [0, 1]:
        raise ValueError('%s is not a valid verbose input. Choose 0 for none or 1 for full' % verbose_int)
    verbose = True if verbose_int == 1 else False
    # TODO: Checker to make sure output path isn't temp folder path
    if not os.path.isdir(output_path):
        print('Output path not found. Creating directory...')
        os.makedirs(output_path, exist_ok=True)

    if not os.path.isfile(timing_model):
        raise FileNotFoundError('Timing model %s is not found' % timing_model)

    if not os.path.isfile(arrow_model):
        raise FileNotFoundError('Arrow model %s is not found' % arrow_model)

    if os.path.isfile(input_path) or os.path.isdir(input_path):
        batch = False if os.path.isfile(input_path) else True
        tmp_folder_name = "_tmp"
        __build_tmp_folder(tmp_folder_name)
        __copy_to_tmp_folder(input_path, tmp_folder_name, batch)
        if verbose:
            print("Starting audio to txt generation\n-----------------------------------------\n")
        try:
            __generate_notes(output_path, tmp_folder_name, timing_model, arrow_model, scalers_path, verbose_int)
            rmtree(tmp_folder_name, ignore_errors=True)
        finally:
            pass
    else:
        raise FileNotFoundError('Audio file(s) path %s not found' % input_path)
    end_time = time.time()
    if verbose:
        print("Elapsed time was %g seconds\n" % (end_time - start_time))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Generate .txt (eventually .sm) files from audio tracks")
    parser.add_argument("-i", "--input",
                        type=str,
                        help="input audio files path")
    parser.add_argument("-o", "--output",
                        type=str,
                        help="output .txt file path")
    parser.add_argument("-s", "--scalers",
                        type=str,
                        default="testing_files/",
                        help="scalers used in training path")
    parser.add_argument("--timing_model",
                        type=str,
                        default="models/timing_model.h5",
                        help="trained timing model path")
    parser.add_argument("--arrow_model",
                        type=str,
                        default="models/retrained_arrow_model.h5",
                        help="trained arrow model path")
    parser.add_argument("-v", "--verbose",
                        type=int,
                        default=0,
                        help="verbosity: 0 - none, 1 - full")
    args = parser.parse_args()

    stepmania_note_generator(args.input,
                             args.output,
                             args.scalers,
                             args.timing_model,
                             args.arrow_model,
                             args.verbose)
