
# ## HOW TO USE:
# # - SPECIFY THE DIRECTORY WHERE THE FILES ARE LOCATED
# # - ARROW LEFT AND ARROW RIGHT TO SWITCH BETWEEN SCENES
# # - PRESS 'T' TO TOGGLE BETWEEN 3 SIGMA AND FIXED PERCENTILE OF BACKSCATTER VALUES

# # USED IN ENVRIOMENT WITH
# #   - GDAL 3.8.3
# #   - Python 3.8.10
# #   - numpy 1.26.4
# #   - matplotlib 3.8.2
# #   - cmocean (https://matplotlib.org/cmocean/)



import os
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from osgeo import gdal
import cmocean
import sys
import matplotlib.colors as mcolors
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.ticker as ticker

gdal.UseExceptions()
gdal.PushErrorHandler('CPLQuietErrorHandler')

class GeoTIFFViewer:
    def __init__(self, directory):
        # Load files/folders
        self.folder_list = sorted([folder for folder in os.listdir(directory) if os.path.isdir(os.path.join(directory, folder))])

        # Update subplot grid to 2 rows x 4 columns
        self.fig, self.ax = plt.subplots(2, 4, figsize=(23, 11))  # Increased figsize to accommodate more subplots

        self.slider_ax = plt.axes([0.2, 0.94, 0.65, 0.03])  # Adjusted position for slider
        self.slider = Slider(self.slider_ax, 'Image Index', 0, len(self.folder_list) - 1, valinit=0, valstep=1)
        
        self.minmax_toggle = False
        self.sigma_level = 4

        # Initialize a list to store colorbars
        self.colorbars = []
        
        # Key press/slider functionality setup
        self.slider.on_changed(self.update)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)

        self.update(0)

    def update(self, val):
        self.current_folder_index = int(val)
        self.load_geotiff(directory)
        self.current_scenename = self.file_list[0].replace('.tif', '')  # Define current_scenename
        self.toggle_limits()
        self.update_display()

    def load_geotiff(self, directory):
        # Get file paths for current image
        current_folder = self.folder_list[self.current_folder_index]
        current_folder_path = os.path.join(directory, current_folder)
        self.file_list = sorted([file for file in os.listdir(current_folder_path) if file.endswith('.tif')])

        print("Current scene at idx", self.current_folder_index, ":", self.file_list[0].replace('.tif', ''))

        # Load GeoTIFF files
        self.subset_1_1, self.subset_1_2 = self.load_bands(current_folder_path, self.file_list, 'RAW')
        self.subset_2_1, self.subset_2_2 = self.load_bands(current_folder_path, self.file_list, 'SNAP')
        self.subset_3_1, self.subset_3_2 = self.load_bands(current_folder_path, self.file_list, 'DIMA')
        self.subset_4_1, self.subset_4_2 = self.load_bands(current_folder_path, self.file_list, 'ANTON')

    def load_bands(self, folder_path, file_list, suffix):

        # Find the index of the file with the specified suffix
        index = [i for i, file in enumerate(file_list) if suffix in file][0]
        file_path = os.path.join(folder_path, file_list[index])
        dataset = gdal.Open(file_path)
        band1 = dataset.GetRasterBand(1).ReadAsArray().astype(float)
        band2 = dataset.GetRasterBand(2).ReadAsArray().astype(float)
        return band1, band2

    def on_key(self, event):
        if event.key == 'right':
            self.current_folder_index = (self.current_folder_index + 1) % len(self.folder_list)
        elif event.key == 'left':
            self.current_folder_index = (self.current_folder_index - 1) % len(self.folder_list)
        elif event.key == 'c':
            self.save_as_png()
            # self.save_current_scenename()
        elif event.key in ['1', '2', '3', '4','5']:
            self.sigma_level = int(event.key)
            self.toggle_limits()
            self.update(self.current_folder_index)

        self.slider.set_val(self.current_folder_index)

    def save_as_png(self):
        path = '/mnt/raid01/SAR/Sentinel-1/Arctic/WesternSvalbard/grease_ice_at_shore/'
        path = '/mnt/d/data/pipeline_compare/overviewer_1024_individual/'
        path = path + str(self.current_folder_index) + '_' + self.current_scenename + '.png'
        self.fig.savefig(path, dpi=300, bbox_inches='tight')
        print(f"Saved {self.current_scenename}.png")

    def save_current_scenename(self):
        print(f"Copied product ID {self.current_scenename}, to textfile.")
        with open('/mnt/c/Users/Maximilian Tontsch/Nextcloud/PolarRS/workspace_thesis/txt/big_oil.txt', 'a') as file:
            file.write(self.current_scenename + '\n')
            
    def toggle_limits(self):
        if self.sigma_level in [1, 2, 3]:
            upper = [84.135, 97.725, 99.865]
            lower = [15.865, 2.275, 0.135]

            self.vmin_HH_1 = np.percentile(self.subset_1_1[~np.isnan(self.subset_1_1)], lower[self.sigma_level-1])
            self.vmax_HH_1 = np.percentile(self.subset_1_1[~np.isnan(self.subset_1_1)], upper[self.sigma_level-1])
            self.vmin_HV_1 = np.percentile(self.subset_1_2[~np.isnan(self.subset_1_2)], lower[self.sigma_level-1])
            self.vmax_HV_1 = np.percentile(self.subset_1_2[~np.isnan(self.subset_1_2)], upper[self.sigma_level-1])

            self.vmin_HH_2 = np.percentile(self.subset_2_1[~np.isnan(self.subset_2_1)], lower[self.sigma_level-1])
            self.vmax_HH_2 = np.percentile(self.subset_2_1[~np.isnan(self.subset_2_1)], upper[self.sigma_level-1])
            self.vmin_HV_2 = np.percentile(self.subset_2_2[~np.isnan(self.subset_2_2)], lower[self.sigma_level-1])
            self.vmax_HV_2 = np.percentile(self.subset_2_2[~np.isnan(self.subset_2_2)], upper[self.sigma_level-1])

            self.vmin_HH_3 = np.percentile(self.subset_3_1[~np.isnan(self.subset_3_1)], lower[self.sigma_level-1])
            self.vmax_HH_3 = np.percentile(self.subset_3_1[~np.isnan(self.subset_3_1)], upper[self.sigma_level-1])
            self.vmin_HV_3 = np.percentile(self.subset_3_2[~np.isnan(self.subset_3_2)], lower[self.sigma_level-1])
            self.vmax_HV_3 = np.percentile(self.subset_3_2[~np.isnan(self.subset_3_2)], upper[self.sigma_level-1])
            
            self.vmin_HH_4 = np.percentile(self.subset_4_1[~np.isnan(self.subset_4_1)], lower[self.sigma_level-1])
            self.vmax_HH_4 = np.percentile(self.subset_4_1[~np.isnan(self.subset_4_1)], upper[self.sigma_level-1])
            self.vmin_HV_4 = np.percentile(self.subset_4_2[~np.isnan(self.subset_4_2)], lower[self.sigma_level-1])
            self.vmax_HV_4 = np.percentile(self.subset_4_2[~np.isnan(self.subset_4_2)], upper[self.sigma_level-1])

        elif self.sigma_level == 4:
            # individual limits

            # # Raw
            self.vmin_HH_1 = 13.7
            self.vmax_HH_1 = 28.8
            self.vmin_HV_1 = 13.0
            self.vmax_HV_1 = 21.3

            # SNAP
            self.vmin_HH_2 = -38.4
            self.vmax_HH_2 = -1.4
            self.vmin_HV_2 = -47.6
            self.vmax_HV_2 = -16.7

            self.vmin_HH_2 = -49.3
            self.vmax_HH_2 = -7.9
            self.vmin_HV_2 = -50.1
            self.vmax_HV_2 = -22.2


            # Dima
            # lowest/highest sigma limits from 24 scenes
            self.vmin_HH_3 = -32.8
            self.vmax_HH_3 = -7.9
            self.vmin_HV_3 = -32.8
            self.vmax_HV_3 = -22.3

            # Anton
            # 3sigma limits from 24 scenes
            self.vmin_HH_4 = -32.2
            self.vmax_HH_4 = -9
            self.vmin_HV_4 = -39.3
            self.vmax_HV_4 = -16.6

        elif self.sigma_level == 5:
            # common limits
            # For 24 scenes 256
            # Raw
            self.vmin_HH_1 = 13.7
            self.vmax_HH_1 = 28.8
            self.vmin_HV_1 = 13.0
            self.vmax_HV_1 = 21.3

            vmin_HH = -45
            vmax_HH = -9.4
            vmin_HV = -49.9
            vmax_HV = -19.5

            # Dima
            self.vmin_HH_3 = vmin_HH
            self.vmax_HH_3 = vmax_HH
            self.vmin_HV_3 = vmin_HV
            self.vmax_HV_3 = vmax_HV
            # SNAP
            self.vmin_HH_2 = vmin_HH
            self.vmax_HH_2 = vmax_HH
            self.vmin_HV_2 = vmin_HV
            self.vmax_HV_2 = vmax_HV

            # Anton
            self.vmin_HH_4 = vmin_HH
            self.vmax_HH_4 = vmax_HH
            self.vmin_HV_4 = vmin_HV
            self.vmax_HV_4 = vmax_HV



    def update_display(self):
        # Remove existing colorbars before clearing axes
        for cbar in self.colorbars:
            cbar.remove()
        self.colorbars = []  # Reset the list

        # Clear the old axes contents
        for row in self.ax:
            for ax in row:
                ax.cla()

        # Choose colormap
        cmap = 'grey'

        # Display the images
        im_list = []
        titles = [
            ('HH: Unprocessed', self.subset_1_1, self.vmin_HH_1, self.vmax_HH_1, self.ax[0, 0]),
            ('HV: Unprocessed', self.subset_1_2, self.vmin_HV_1, self.vmax_HV_1, self.ax[1, 0]),
            ('HH: SNAP', self.subset_2_1, self.vmin_HH_2, self.vmax_HH_2, self.ax[0, 1]),
            ('HV: SNAP', self.subset_2_2, self.vmin_HV_2, self.vmax_HV_2, self.ax[1, 1]),
            ('HH: Murashkin', self.subset_3_1, self.vmin_HH_3, self.vmax_HH_3, self.ax[0, 2]),
            ('HV: Murashkin', self.subset_3_2, self.vmin_HV_3, self.vmax_HV_3, self.ax[1, 2]),
            ('HH: Korosov', self.subset_4_1, self.vmin_HH_4, self.vmax_HH_4, self.ax[0, 3]),
            ('HV: Korosov', self.subset_4_2, self.vmin_HV_4, self.vmax_HV_4, self.ax[1, 3]),
        ]

        for idx, (title, subset, vmin, vmax, axis) in enumerate(titles):
            im = axis.imshow(subset, cmap=cmap, vmin=vmin, vmax=vmax)
            axis.set_xticks([])
            axis.set_yticks([])
            axis.set_title(title)
            # Create and store the colorbar
            divider = make_axes_locatable(axis) 
            cax = divider.append_axes("right", size="5%", pad=0.05)
            cbar = plt.colorbar(im, cax=cax)
            cbar.ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            cbar.update_ticks()
            if idx == 1 or idx == 0:
                cbar.set_label('10 log$_{10}$(DN)')
            else:
                cbar.set_label(r'$\sigma_0$ [dB]')
            self.colorbars.append(cbar)
            
        # Display title
        date, time, sat = self.get_date_and_sat_from_filename(self.folder_list[self.current_folder_index])
        suptitle = f'{sat} | {date} | {time}'
       # Display subplottitle
        title_limits = {
                    5: 'common limits',
                    4: 'individual limits',
                    3: "image 3$\sigma$ limits",
                    2: "image 2$\sigma$ limits",
                    1: "image 1$\sigma$ limits"
                }
        suptitle += f' | {title_limits[self.sigma_level]}'

        self.fig.suptitle(suptitle, fontsize=20, y=0.99)

        # layout adjustment
        self.fig.subplots_adjust(top=0.935,
                bottom=0.0,
                left=0.02,
                right=0.96,
                hspace=0.0,
                wspace=0.13)

    def get_date_and_sat_from_filename(self, file_name):

        # YYYYMMDD_HHMMSS_S1A scheme
        date_part = file_name[0:8]
        time_part = file_name[9:15]
        sat_part = file_name[16:19]

        date = f"{date_part[6:8]}.{date_part[4:6]}.{date_part[:4]}"
        time = f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}"
        if sat_part == 'S1A':
            sat = 'Sentinel-1A'
        elif sat_part == 'S1B':
            sat = 'Sentinel-1B'
        else:
            sat = 'Code and filenames dont match!'
        return date, time, sat

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python GeoTIFF_Viewer_comparison_quadruple.py <path_to_directory>")
        sys.exit(1)

    directory = sys.argv[1]
    viewer = GeoTIFFViewer(directory)
    plt.show()
    print("Finished")



