import sys
import os
import argparse
from sentinel1_routines.download import download_single_scene

# ... (your existing functions and imports)
# takes a list of .zip products in .txt file and saves it in an string array
def read_lines_to_array(file_path):
    lines_array = []
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            lines_array.append(line)
    return lines_array

def get_scene_names(scene_names_file_path, single_scene_name):
    if scene_names_file_path:
        return read_lines_to_array(scene_names_file_path)
    elif single_scene_name:
        return single_scene_name.split(',')
    else:
        raise ValueError("Please provide either the scene_names_file_path or a single_scene_name as input argument.")

if __name__ == "__main__":
    # Create an argument parser
    parser = argparse.ArgumentParser(description="Download Sentinel-1 scenes.")

    # Add an argument for the scene names file
    parser.add_argument(
        "--scene_names_file_path",
        "-snp",
        type=str,
        help="Path to the .txt file containing scene names, one per line.",
    )

    # Add an argument for the scene names provided as a comma-separated string
    parser.add_argument(
        "--single_scene_name",
        "-sn",
        type=str,
        help="Single scene name to download from ASF.",
    )

    # Parse the command-line arguments
    args = parser.parse_args()

    # Get scene names either from the file or from provided_scene_names argument
    scene_names = get_scene_names(args.scene_names_file_path, args.single_scene_name)

    # Set output folder
    output_folder = '/mnt/raid01/SAR/Sentinel-1/Arctic/WesternSvalbard/raw_root/'
    root_folder = '/mnt/raid01/SAR/Sentinel-1/Arctic/WesternSvalbard/raw_root/'

    # Set the environment variable
    os.environ['ASF_CREDENTIALS'] = '/home/mtontsch/Documents/asf_cred.txt'

    # Iterate over the scene names and download each scene
    for scene_name in scene_names:
        download_single_scene(scene_name, root_folder=root_folder, output_folder=output_folder)
