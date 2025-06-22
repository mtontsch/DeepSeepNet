import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from osgeo import gdal
import cmocean

gdal.UseExceptions()
gdal.PushErrorHandler('CPLQuietErrorHandler')


class GeoTIFFViewer:
    def __init__(self, directory):
        # Load files
        self.file_list = sorted([file for file in os.listdir(directory) if file.endswith('.tif') or file.endswith('.tiff')])
        # sort file list by date and time 
        self.file_list.sort(key=lambda x: (x[17:25], x[26:32]))
        
        figsize = 1
        self.fig, self.ax = plt.subplots(1, 2, figsize=(8, 7)*figsize)
        # self.fig.canvas.manager.window.move(2200, 50)

        self.slider_ax = plt.axes([0.2, 0.9, 0.65, 0.03])
        self.slider = Slider(self.slider_ax, 'Image Index', 0, len(self.file_list) - 1, valinit=0, valstep=1)

        # Set initial values for vmin and vmax
        self.vmin_HH = -40
        self.vmax_HH = 0
        self.vmin_HV = -50
        self.vmax_HV = -20
        self.minmax_toggle = False
        self.sigma_level = 4

        # Key press/slider functionality setup
        self.slider.on_changed(self.update)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)

        self.update(0)

    def on_key(self, event):
        if event.key == 'right':
            self.current_file_index = (self.current_file_index + 1) % len(self.file_list)
        elif event.key == 'left':
            self.current_file_index = (self.current_file_index - 1) % len(self.file_list)
        elif event.key == 'c':
            self.save_current_scenename()
        elif event.key in ['1', '2', '3', '4']:
            self.sigma_level = int(event.key)
            self.toggle_limits()
            self.update(self.current_file_index)
            print(f'Sigma level set to: {self.sigma_level}')
            print(self.vmin_HH, self.vmax_HH, self.vmin_HV, self.vmax_HV)

        self.slider.set_val(self.current_file_index)

    def save_current_scenename(self):
        #if self.current_file_index < len(self.file_list):
        print(f"Copied product ID {self.current_scenename}, to textfile.")
        with open('/mnt/c/Users/Maximilian Tontsch/Nextcloud/PolarRS/workspace_thesis/txt/big_oil.txt', 'a') as file:
            file.write(self.current_scenename + '\n')

    def toggle_limits(self):

        # Toggle between minmax and sigma clipping
        if self.sigma_level in [1, 2, 3]:
            upper = [84.135, 97.725, 99.865]
            lower = [15.865, 2.275, 0.135]


            self.vmin_HH = np.percentile(self.subset_1[~np.isnan(self.subset_1)], lower[self.sigma_level-1])
            self.vmax_HH = np.percentile(self.subset_1[~np.isnan(self.subset_1)], upper[self.sigma_level-1])
            
            self.vmin_HV = np.percentile(self.subset_2[~np.isnan(self.subset_2)], lower[self.sigma_level-1])
            self.vmax_HV = np.percentile(self.subset_2[~np.isnan(self.subset_2)], upper[self.sigma_level-1])
            print(f'Percentile values for HH: {self.vmin_HH}, {self.vmax_HH}')
            print(f'Percentile values for HV: {self.vmin_HV}, {self.vmax_HV}')

        elif self.sigma_level == 4:
            self.vmin_HH = -38.4
            self.vmax_HH = -1.4
            self.vmin_HV = -47.6
            self.vmax_HV = -16.7

    def update(self, val):  
        self.current_file_index = int(val)
        self.load_geotiff(directory)
        self.toggle_limits()        
        self.update_display()

    def load_geotiff(self, directory):

        self.current_scenename = self.file_list[self.current_file_index].replace('.tif', '')
        # Get file path for current image
        file_path_1 = os.path.join(directory, self.file_list[self.current_file_index])

        # Load geotiff data into numpy ndarray arrays
        dataset_1 = gdal.Open(file_path_1)
        self.subset_1 = dataset_1.GetRasterBand(1).ReadAsArray().astype(float)  
        self.subset_2 = dataset_1.GetRasterBand(2).ReadAsArray().astype(float) 

        # If incidence channel is present
        if dataset_1.RasterCount > 2:
            self.subset_3 = dataset_1.GetRasterBand(3).ReadAsArray().astype(float)
            # mean of third channel
            self.mean_inc_angle = np.nanmean(self.subset_3)

        # print(f'Number of nan values in subset_1: {np.sum(np.isnan(self.subset_1))}')


        # self.subset_1 = 20 * np.log10(self.subset_1)
        # self.subset_2 = 20 * np.log10(self.subset_2)
        # self.subset_1 = np.where(np.isnan(self.subset_1), np.nan, 10 * np.log10(self.subset_1))
        # self.subset_2 = np.where(np.isnan(self.subset_2), np.nan, 10 * np.log10(self.subset_2))


    def update_display(self):

        # Clear the old axes contents
        self.ax[0].cla()
        self.ax[1].cla()
        if hasattr(self, 'cbar1'):
            self.cbar1.ax.cla()
        if hasattr(self, 'cbar2'):
            self.cbar2.ax.cla()

        # choose colormap
        cmap = 'viridis'
        cmap = cmocean.cm.deep_r
        cmap = cmocean.cm.ice
        cmap = 'grey'

        # Display the images
        self.im1 = self.ax[0].imshow(self.subset_1, cmap=cmap, vmin=self.vmin_HH, vmax=self.vmax_HH)
        self.im2 = self.ax[1].imshow(self.subset_2, cmap=cmap, vmin=self.vmin_HV, vmax=self.vmax_HV)


        # Remove ticks
        self.ax[0].set_xticks([])
        self.ax[0].set_yticks([])
        self.ax[1].set_xticks([])
        self.ax[1].set_yticks([])

        # Display colorbars
        self.cbar1 = self.fig.colorbar(self.im1, ax=self.ax[0], orientation='horizontal', cax=self.ax[0].inset_axes([0.1, -0.1, 0.8, 0.05]))
        self.cbar1.set_label(r'$\sigma^0$ [dB]')
        self.cbar2 = self.fig.colorbar(self.im2, ax=self.ax[1], orientation='horizontal', cax=self.ax[1].inset_axes([0.1, -0.1, 0.8, 0.05]))
        self.cbar2.set_label(r'$\sigma^0$ [dB]')
        
        # Display title
        date, time, sat = self.get_date_and_sat_from_filename(self.file_list[self.current_file_index])
        print(f"Current image: {self.file_list[self.current_file_index]}")
        print("----------------------------------------------")
        suptitle = f'{sat} | {date} | {time} '
        if hasattr(self, 'mean_inc_angle'):
            suptitle += f'| Mean incidence angle: {self.mean_inc_angle:.2f}'
        self.fig.suptitle(suptitle, fontsize=16)
        
        # Display subplottitle


        titles = {
            3: f'(3 sigma clipped [{self.vmin_HH:.1f}, {self.vmax_HH:.1f}])',
            2: f'(2 sigma clipped [{self.vmin_HH:.1f}, {self.vmax_HH:.1f}])',
            1: f'(1 sigma clipped [{self.vmin_HH:.1f}, {self.vmax_HH:.1f}])',
            4: f'(manual limits [{self.vmin_HH:.1f}, {self.vmax_HH:.1f}])'
        }
        self.ax[0].set_title(f'HH {titles[self.sigma_level]}')
        self.ax[1].set_title(f'HV {titles[self.sigma_level]}')


    def get_date_and_sat_from_filename(self, file_name):
        
        # OG S1 name scheme
        date_part = file_name[17:25]
        time_part = file_name[26:32]
        sat_part = file_name[0:3]

        # YYYYMMDD_HHMMSS_S1A scheme
        # date_part = file_name[0:8]
        # time_part = file_name[9:15]
        # sat_part = file_name[16:19]       

        date = f"{date_part[6:8]}.{date_part[4:6]}.{date_part[:4]}"
        time = f"{time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}"
        if sat_part == 'S1A':
            sat = 'Sentinel-1A'
        elif sat_part == 'S1B':
            sat = 'Sentinel-1B'
        elif sat_part == 'S1C':
            sat = 'Sentinel-1C'
        else:
            sat = 'Code and filenames dont match!'
        return date, time, sat


if __name__ == '__main__':
    
    directory = '/mnt/f/PolarRS/dataset_6/geotiffs_1024'
    directory = '/mnt/d/data_2/output_scott_2025/'

    viewer = GeoTIFFViewer(directory)

    plt.subplots_adjust(top=1.0, bottom=0.019, left=0.015, right=0.985, hspace=0.2, wspace=0.031)
    plt.show()
    
    print("Finished")