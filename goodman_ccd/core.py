from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
import os
import re
import sys
import time
import glob
import random
import logging
import ccdproc
import numpy as np
import matplotlib
matplotlib.use('GTK3Agg')
from matplotlib import pyplot as plt
from ccdproc import CCDData
from astropy.coordinates import EarthLocation
from astropy.time import Time, TimeDelta
from astroplan import Observer
from astropy import units as u
from astropy.modeling import (models, fitting, Model)

from scipy import signal

log = logging.getLogger('goodmanccd.core')


def convert_time(in_time):
    """Converts time to seconds since epoch

    Args:
        in_time (str): time obtained from header's keyword DATE-OBS

    Returns:
        time in seconds since epoch

    """
    return time.mktime(time.strptime(in_time, "%Y-%m-%dT%H:%M:%S.%f"))


def fix_duplicated_keywords(night_dir):
    """Remove duplicated keywords

    There are some cases when the raw data comes with duplicated keywords.
    The origin has not been tracked down. The solution is to identify the
    duplicated keywords and the remove all but one from the end backwards.

    Args:
        night_dir (str): The full path for the raw data location

    """
    log.info('Finding duplicated keywords')
    log.warning('Files will be overwritten')
    files = glob.glob(os.path.join(night_dir, '*.fits'))
    # Pick a random file to find duplicated keywords
    random_file = random.choice(files)
    ccd = CCDData.read(random_file)
    header = ccd.header
    # Put the duplicated keywords in a list
    multiple_keys = []
    for keyword in header.keys():
        if keyword != '':
            if header.count(keyword) > 1:
                if keyword not in multiple_keys:
                    multiple_keys.append(keyword)
    if multiple_keys != []:
        log.info('Found {:d} duplicated keyword{:s}'.format(len(multiple_keys),
                                                            's' if len(multiple_keys) > 1 else ''))
        for image_file in files:
            log.debug('Processing Image File: {:s}'.format(image_file))
            try:
                ccd = CCDData.read(image_file)
                for keyword in multiple_keys:
                    while ccd.header.count(keyword) > 1:
                        ccd.header.remove(keyword,
                                          ccd.header.count(keyword) - 1)
                log.warning('Overwriting file with duplicated keywords removed')
                log.debug('File %s overwritten', image_file)
                ccd.write(image_file, clobber=True)
            except IOError as error:
                log.error(error)


def ra_dec_to_deg(right_ascension, declination):
    """Converts right ascension and declination to degrees

    Args:
        right_ascension (str): Right ascension in the format hh:mm:ss.sss
        declination (str): Declination in the format dd:mm:ss.sss

    Returns:
        right_ascension_deg (float): Right ascension in degrees
        declination_deg (float): Declination in degrees

    """
    right_ascension = right_ascension.split(":")
    declination = declination.split(":")
    # RIGHT ASCENTION conversion
    right_ascension_deg = (float(right_ascension[0])
                           + (float(right_ascension[1])
                              + (float(right_ascension[2]) / 60.)) / 60.) * (360. / 24.)
    # DECLINATION conversion
    # sign = float(declination[0]) / abs(float(declination[0]))
    if float(declination[0]) == abs(float(declination[0])):
        sign = 1
    else:
        sign = -1
    declination_deg = sign * (abs(float(declination[0]))
                              + (float(declination[1])
                                 + (float(declination[2]) / 60.)) / 60.)
    return right_ascension_deg, declination_deg


def print_spacers(message):
    """Miscelaneous function to print uniform spacers

    Prints a spacer of 80 columns with  and 3 rows height. The first and last
    rows contains the symbol "=" repeated 80 times. The middle row contains the
    message centered and the extremes has one single "=" symbol.
    The only functionality of this is aesthetic.

    Args:
        message (str): A message to be printed

    Returns:
        True (bool): A True value

    """

    columns = 80
    if len(message) % 2 == 1 and int(columns) % 2 != 1:
        message += " "
    bar_length = int(columns)
    spacer_bar = "=" * bar_length
    blanks = bar_length - 2
    space_length = int((blanks - len(message)) / 2)
    message_bar = "=" + " " * space_length + message + " " * space_length + "="
    print(spacer_bar)

    print(message_bar)
    print(spacer_bar)
    return True


def print_progress(current, total):
    """Prints the percentage of a progress

    It works for FOR loops, requires to know the full length of the loop.
    Prints to the standard output.

    Args:
        current (int): Current value in the range of the loop.
        total (int): The length of the loop.

    Returns:
        Nothing

    """
    if current == total:
        sys.stdout.write("Progress {:.2%}\n".format(1.0 * current / total))
    else:
        sys.stdout.write("\rProgress {:.2%}".format(1.0 * current / total))
    sys.stdout.flush()
    return


def get_twilight_time(date_obs):
    """Get end/start time of evening/morning twilight

    Notes:
        Taken from David Sanmartim's development

    Args:
        date_obs (list): List of all the dates from data.

    Returns:
        twilight_evening (str): Evening twilight time in the format 'YYYY-MM-DDTHH:MM:SS.SS'
        twilight_morning (str): Morning twilight time in the format 'YYYY-MM-DDTHH:MM:SS.SS'
        sun_set_time (str): Sun set time in the format 'YYYY-MM-DDTHH:MM:SS.SS'
        sun_rise_time (str): Sun rise time in the format 'YYYY-MM-DDTHH:MM:SS.SS'

    """
    # observatory(str): Observatory name.
    observatory = 'SOAR Telescope'
    geodetic_location = ['-70d44m01.11s', '-30d14m16.41s', 2748]
    # longitude (str): Geographic longitude in string format
    longitude = geodetic_location[0]
    # latitude (str): Geographic latitude in string format.
    latitude = geodetic_location[1]
    # elevation (int): Geographic elevation in meters above sea level
    elevation = geodetic_location[2]
    # timezone (str): Time zone.
    timezone = 'UTC'
    # description(str): Observatory description
    description = 'Soar Telescope on Cerro Pachon, Chile'

    soar_loc = EarthLocation.from_geodetic(longitude,
                                           latitude,
                                           elevation * u.m,
                                           ellipsoid='WGS84')

    soar = Observer(name=observatory,
                    location=soar_loc,
                    timezone=timezone,
                    description=description)

    time_first_frame, time_last_frame = Time(min(date_obs)), Time(max(date_obs))

    twilight_evening = soar.twilight_evening_astronomical(Time(time_first_frame),
                                                          which='nearest').isot
    twilight_morning = soar.twilight_morning_astronomical(Time(time_last_frame),
                                                          which='nearest').isot
    sun_set_time = soar.sun_set_time(Time(time_first_frame),
                                     which='nearest').isot
    sun_rise_time = soar.sun_rise_time(Time(time_last_frame),
                                       which='nearest').isot
    log.debug('Sun Set ' + sun_set_time)
    log.debug('Sun Rise ' + sun_rise_time)
    return twilight_evening, twilight_morning, sun_set_time, sun_rise_time


def image_overscan(ccd, overscan_region, add_keyword=False):
    """Apply overscan to data

    Args:
        ccd (object): A ccdproc.CCDData instance
        overscan_region (str): The overscan region in the format '[x1:x2,y1:y2]'
        where x is the spectral axis and y is the spatial axis.
        add_keyword (bool): Tells ccdproc whether to add a keyword or not.
        Default False.

    Returns:
        ccd (object): Overscan corrected ccdproc.CCDData instance

    """
    ccd = ccdproc.subtract_overscan(ccd=ccd,
                                    median=True,
                                    fits_section=overscan_region,
                                    add_keyword=add_keyword)
    ccd.header.add_history('Applied overscan correction ' + overscan_region)
    return ccd


def image_trim(ccd, trim_section, add_keyword=False):
    """Trim image to a given section

    Args:
        ccd (object): A ccdproc.CCDData instance
        trim_section (str): The trimming section in the format '[x1:x2,y1:y2]'
        where x is the spectral axis and y is the spatial axis.
        add_keyword (bool): Tells ccdproc whether to add a keyword or not.
        Default False.

    Returns:
        ccd (object): Trimmed ccdproc.CCDData instance

    """
    ccd = ccdproc.trim_image(ccd=ccd,
                             fits_section=trim_section,
                             add_keyword=add_keyword)
    ccd.header.add_history('Trimmed image to ' + trim_section)
    return ccd


def get_slit_trim_section(master_flat):
    """Find the slit edges to trim all data

    Using a master flat, ideally good signal to noise ratio, this function will
    identify the edges of the slit projected into the detector. Having this data
    will allow to reduce the overall processing time and also reduce the
    introduction of artifacts due to non-illuminated regions in the detectors,
    such as NaNs -INF +INF, etc.

    Args:
        master_flat (object): A ccdproc.CCDData instance

    Returns:
        slit_trim_section (str): Trim section in spatial direction in the format
        [:,slit_lower_limit:slit_higher_limit]

    """
    x, y = master_flat.data.shape
    # Using the middle point to make calculations, usually flats have good
    # illumination already at the middle.
    middle = int(y / 2.)
    ccd_section = master_flat.data[:, middle:middle + 200]
    ccd_section_median = np.median(ccd_section, axis=1)
    # spatial_axis = range(len(ccd_section_median))

    # Spatial half will be used later to constrain the detection of the first
    # edge before the first half.
    spatial_half = len(ccd_section_median) / 2.
    # pseudo-derivative to help finding the edges.
    pseudo_derivative = np.array(
        [abs(ccd_section_median[i + 1] - ccd_section_median[i]) for i in range(0, len(ccd_section_median) - 1)])
    filtered_data = np.where(np.abs(pseudo_derivative > 0.5 * pseudo_derivative.max()),
                             pseudo_derivative,
                             None)
    peaks = signal.argrelmax(filtered_data, axis=0, order=3)[0]
    # print(peaks)

    slit_trim_section = None
    if len(peaks) > 2 or peaks == []:
        log.debug('No trim section')
    else:
        # print(peaks, flat_files.grating[flat_files.file == file], flat_files.slit[flat_files.file == file])
        if len(peaks) == 2:
            # This is the ideal case, when the two edges of the slit are found.
            low, high = peaks
            slit_trim_section = '[:,{:d}:{:d}]'.format(low, high)
        elif len(peaks) == 1:
            # when only one peak is found it will choose the largest region from the spatial axis center to one edge.
            if peaks[0] <= spatial_half:
                slit_trim_section = '[:,{:d}:{:d}]'.format(peaks[0], len(ccd_section_median))
            else:
                slit_trim_section = '[:,{:d}:{:d}]'.format(0, peaks[0])
    return slit_trim_section


def cosmicray_rejection(ccd, mask_only=False):
    """Do cosmic ray rejection

      Notes:
          OBS: cosmic ray rejection is working pretty well by defining gain = 1.
          It's not working when we use the real gain of the image. In this case
          the sky level changes by a factor equal the gain.
          Function to determine the sigfrac and objlim: y = 0.16 * exptime + 1.2

      Args:
          ccd (object): CCDData Object
          mask_only (bool): In some cases you may want to obtain the cosmic
          rays mask only

      Returns:
          ccd (object): The modified CCDData object

      """
    # TODO (simon): Validate this method
    if ccd.header['OBSTYPE'] == 'OBJECT':
        value = 0.16 * float(ccd.header['EXPTIME']) + 1.2
        log.info('Cleaning cosmic rays... ')
        # ccd.data= ccdproc.cosmicray_lacosmic(ccd, sigclip=2.5, sigfrac=value, objlim=value,
        ccd.data, mask = ccdproc.cosmicray_lacosmic(ccd.data, sigclip=2.5, sigfrac=value, objlim=value,
                                                     gain=float(ccd.header['GAIN']),
                                                     readnoise=float(ccd.header['RDNOISE']),
                                                     satlevel=np.inf, sepmed=True, fsmode='median',
                                                     psfmodel='gaussy', verbose=False)
        ccd.header.add_history("Cosmic rays rejected with LACosmic")
        log.info("Cosmic rays rejected with LACosmic")
        if mask_only:
            return mask
        else:
            return ccd
    else:
        log.info('Skipping cosmic ray rejection for image of datatype: {:s}'.format(ccd.header['OBSTYPE']))
        return ccd



def get_best_flat(flat_name):
    """Look for matching master flat

    Given a basename for masterflats this function will find the name of the
    files that matches the base name and then will choose the first. Ideally
    this should go further as to check signal, time gap, etc.
    After it identifies the file it will load it using ccdproc.CCDData and
    return it along the filename.
    In case if fails it will return None instead of master_flat and another
    None instead of master_flat_name.

    Args:
        flat_name (str): Full path of masterflat basename. Ends in '*.fits'.

    Returns:
        master_flat (object): A ccdproc.CCDData instance
        master_flat_name (str): Full path to the chosen masterflat.

    """
    flat_list = glob.glob(flat_name)
    log.debug('Flat base name {:s}'.format(flat_name))
    log.debug('Matching master flats found: {:d}'.format(len(flat_list)))
    if len(flat_list) > 0:
        if len(flat_list) == 1:
            master_flat_name = flat_list[0]
        else:
            master_flat_name = flat_list[0]
        # elif any('dome' in flat for flat in flat_list):
        #     master_flat_name =

        master_flat = CCDData.read(master_flat_name, unit=u.adu)
        log.info('Found suitable master flat: {:s}'.format(master_flat_name))
        return master_flat, master_flat_name
    else:
        log.error('There is no flat available')
        return None, None


def print_default_args(args):
    """Print default values of arguments.

    This is mostly helpful for debug but people not familiar with the software
    might find it useful as well

    Args:
        args (object): An argparse instance

    """
    arg_name = {'auto_clean': '--auto-clean',
                'clean_cosmic': '-c, --cosmic',
                'debug_mode': '--debug',
                'flat_normalize': '--flat-normalize',
                'ignore_bias': '--ignore-bias',
                'log_to_file': '--log-to-file',
                'norm_order': '--flat-norm-order',
                'raw_path': '--raw-path',
                'red_path': '--red-path',
                'saturation_limit': '--saturation',
                'destiny': '-d --proc-path',
                'interactive_ws': '-i --interactive',
                'lamp_all_night': '-r --reference-lamp',
                'lamp_file': '-l --lamp-file',
                'output_prefix': '-o --output-prefix',
                'pattern': '-s --search-pattern',
                'procmode': '-m --proc-mode',
                'reference_dir': '-R --reference-files',
                'source': '-p --data-path',
                'save_plots': '--save-plots' }
    for key in args.__dict__:
        log.info('Default value for {:s} is {:s}'.format(arg_name[key],
                                       str(args.__getattribute__(key))))


def normalize_master_flat(master, name, method='simple', order=15):
    """ Master flat normalization method

    This function normalize a master flat in three possible ways:
     _mean_: simply divide the data by its mean

     _simple_: Calculates the median along the spatial axis in order to obtain
     the dispersion profile. Then fits a Chebyshev1D model and apply this to all
     the data.

     _full_: This is for experimental purposes only because it takes a lot of
     time to process. It will fit a model to each line along the dispersion axis
     and then divide it by the fitted model. I do not recommend this method
     unless you have a good reason as well as a powerful computer.

    Args:
        master (object): Master flat. Has to be a ccdproc.CCDData instance
        name (str): Full path of master flat prior to normalization
        method (str): Normalization method, 'mean', 'simple' or 'full'
        order (int): Order of the polinomial to be fitted.

    Returns:
        master (object):  The normalized master flat. ccdproc.CCDData instance

    """
    assert isinstance(master, CCDData)

    # define new name, base path and full new name
    new_name = 'norm_' + name.split('/')[-1]
    path = '/'.join(name.split('/')[0:-1])
    norm_name = os.path.join(path, new_name)

    if method == 'mean':
        log.info('Normalizing by mean')
        master.data /= master.data.mean()

        master.header.add_history('Flat Normalized by Mean')

    elif method == 'simple' or method == 'full':
        log.info('Normalizing flat by {:s} model'.format(method))

        # Initialize Fitting models and fitter
        model_init = models.Chebyshev1D(degree=order)
        model_fitter = fitting.LevMarLSQFitter()

        # get data shape
        x_size, y_size = master.data.shape
        x_axis = range(y_size)

        if method == 'simple':
            # get profile along dispersion axis to fit a model to use for
            # normalization
            profile = np.median(master.data, axis=0)

            # do the actual fit
            fit = model_fitter(model_init, x_axis, profile)

            # convert fit into an array
            fit_array = fit(x_axis)

            # pythonic way to divide an array by a vector
            master.data = master.data / fit_array[None, :]

            master.header.add_history('Flat Normalized by simple model')

        elif method == 'full':
            log.warning('This part of the code was left here for experimental '
                        'purposes only')
            log.info('This procedure takes a lot to process, you might want to'
                     'see other method such as simple or mean.')
            for i in range(x_size):
                fit = model_fitter(model_init, x_axis, master.data[i])
                master.data[i] = master.data[i] / fit(x_axis)
            master.header.add_history('Flat Normalized by full model')

    # write normalized flat to a file
    master.write(norm_name, clobber=True)

    return master

# spectroscopy specific functions

def identify_targets(ccd, plots=False):
    """Identify targets cross correlating spatial profile with a gaussian model

    The method of cross-correlating a gaussian model to the spatial profile was
    mentioned in Marsh 1989, then I created my own implementation. The spatial
    profile is obtained by finding the median across the full dispersion axis.
    For goodman the spectrum and ccd are very well aligned, there is a slight
    variation from one configuration to another but in general is acceptable.

    Args:
        ccd (object): a ccdproc.CCDData instance

    Returns:
        profile_model (object): an astropy.modeling.Model instance, it could be
        a Gaussian1D or CompoundModel (several Gaussian1D). Each of them
        represent a point source spectrum found.

    """
    if isinstance(ccd, CCDData):
        slit_size = re.sub('[a-zA-Z"]', '', ccd.header['SLIT'])
        serial_binning = int(ccd.header['CCDSUM'].split()[0])
        # order will be used for finding the peaks later but also as an initial
        # estimate for stddev of gaussian
        order = int(round(float(slit_size) / (0.15 * serial_binning)))
        # averaging overall spectral dimension because in goodman the spectra is
        # deviated very little
        profile_median = np.median(ccd.data, axis=1)

        # Gaussian has to be defined at the middle for it to work
        gaussian = models.Gaussian1D(amplitude=profile_median.max(),
                                     mean=profile_median.size // 2,
                                     stddev=order).rename('Gaussian')

        # do cross correlation of data with gaussian
        # this is useful for cases with low signal to noise ratio
        cross_corr = signal.correlate(in1=profile_median,
                                      in2=gaussian(range(profile_median.size)),
                                      mode='same')
        # filter cross correlation data
        filt_cross_corr = np.where(np.abs(cross_corr > cross_corr.min()
                                          + 0.03 * cross_corr.max()),
                                   cross_corr,
                                   None)
        peaks = signal.argrelmax(filt_cross_corr, axis=0, order=order)[0]

        profile_model = None
        for i in range(len(peaks)):
            low_lim = np.max([0, peaks[i] - 5])
            hig_lim = np.min([peaks[i] + 5, profile_median.size])
            amplitude = profile_median[low_lim: hig_lim].max()
            gaussian = models.Gaussian1D(amplitude=amplitude,
                                         mean=peaks[i],
                                         stddev=order).rename('Gaussian_'
                                                              '{:d}'.format(i))
            if profile_model is not None:
                profile_model += gaussian
            else:
                profile_model = gaussian
        #     plt.axvline(peaks[i])
        # print(profile_model)

        # fit model to profile
        fit_gaussian = fitting.LevMarLSQFitter()
        profile_model = fit_gaussian(model=profile_model,
                                     x=range(profile_median.size),
                                     y=profile_median)
        # print(fit_gaussian.fit_info)
        if plots:
            # plt.plot(cross_corr, label='Cross Correlation', linestyle='--')
            plt.plot(profile_model(range(profile_median.size)),
                     label='Fitted Model')
            plt.plot(profile_median, label='Profile (median)', linestyle='--')
            plt.legend(loc='best')
            plt.show()

        # print(profile_model)
        if fit_gaussian.fit_info['ierr'] not in [1, 2, 3, 4]:
            log.warning('There is some problem with the fitting.'
                        'Returning None.')
            return None
        else:
            return profile_model

    else:
        log.error('Not a CCDData instance')
        return None


def trace_targets(ccd, profile, sampling_step=5, pol_deg=2, plots=True):
    """Find the trace of the target's spectrum on the image

    Args:
        ccd (object): Instance of ccdproc.CCDData
        profile (object): Instance of astropy.modeling.Model, contains the
        spatial profile of the 2D spectrum.
        sampling_step (int): Frequency of sampling in pixels
        pol_deg (int): Polynomial degree for fitting the trace
        plots (bool): If True will show plots (debugging)

    Returns:

    """
    # added two assert for debugging purposes
    assert isinstance(ccd, CCDData)
    assert isinstance(profile, Model)

    # Get image dimensions
    spatial_length, dispersion_length = ccd.data.shape

    # Initialize model fitter
    model_fitter = fitting.LevMarLSQFitter()

    # Initialize the model to fit the traces
    trace_model = models.Polynomial1D(degree=pol_deg)

    # Will store the arrays for the fitted location of the target obtained
    # in the fitting
    trace_points = None

    # List that will contain all the Model instances corresponding to traced
    # targets
    all_traces = None

    # Array defining the points to be sampled
    sampling_axis = range(0,
                          dispersion_length // sampling_step * sampling_step,
                          sampling_step)

    # Loop to go through all the sampling points
    for i in sampling_axis:
        # Fit the inital model to the data
        fitted_profile = model_fitter(model=profile,
                                      x=range(ccd.data[:, i].size),
                                      y=ccd.data[:, i])
        if model_fitter.fit_info['ierr'] not in [1, 2, 3, 4]:
            log.error(
                "Fitting did not work fit_info['ierr'] = \
                {:d}".format(model_fitter.fit_info['ierr']))

        # alternatively could use fitted_profile.param_names
        # the mean_keys is another way to tell how many submodels are in the
        # model that was parsed.
        mean_keys = [key for key in dir(fitted_profile) if 'mean' in key]

        if trace_points is None:
            trace_points = np.ndarray((len(mean_keys),
                                       dispersion_length // sampling_step))

        # store the corresponding value in the proper array for later fitting
        # a low order polinomial
        for e in range(trace_points.shape[0]):
            trace_points[e][i // sampling_step] =\
               fitted_profile.__getattribute__(mean_keys[e]).value

    # fit a low order polynomial for the trace
    for trace_num in range(trace_points.shape[0]):
        fitted_trace = model_fitter(model=trace_model,
                                    x=sampling_axis,
                                    y=trace_points[trace_num])

        fitted_trace.rename('Trace_{:d}'.format(trace_num))

        if model_fitter.fit_info['ierr'] not in [1, 2, 3, 4]:
            log.error(model_fitter.fit_info['ierr'])
        else:
            # RMS Error calculation
            RMSError = np.sqrt(
                np.sum(np.array([fitted_trace(sampling_axis) -
                                 trace_points[trace_num]]) ** 2))
            log.info('Trace Fit RMSE: {:.3f}'.format(RMSError))

            if all_traces is None:
                all_traces = [fitted_trace]
            else:
                all_traces.append(fitted_trace)

        if plots:
            plt.plot(sampling_axis,
                     trace_points[trace_num],
                     marker='o',
                     label='Data Points')
            plt.plot(fitted_trace(range(dispersion_length)),
                     label='Model RMSE: {:.2f}'.format(RMSError))

    if plots:
        plt.title('Targets Trace')
        plt.xlabel('Dispersion Axis')
        plt.ylabel('Spatial Axis')
        plt.imshow(ccd.data, cmap='YlGnBu', clim=(0, 300))

        for trace in trace_points:
            plt.plot(sampling_axis, trace, marker='.', linestyle='--')
            # print(trace)
        plt.legend(loc='best')
        plt.show()
    return all_traces


def get_extraction_zone(ccd, model, n_sigma_extract, plots=False):
    """Get a rectangular CCD zone that contains the spectrum

    Notes:
        For Goodman HTS the alignment of the spectrum with the detector lines
        is quite good, that's why this function does not consider the trace.
        Also because the `model` argument is based on the median throughout all
        the detector along the dispersion axis, so if there is a strong
        misalignment it will result in a wider Gaussian Profile

    Args:
        ccd (object): A ccdproc.CCDData instance, the image from which the zone
         will be extracted
        model (object): An astropy.modeling.Model instance that was previously
         fitted to the spatial profile.
        n_sigma_extract (int): Total number of sigmas to be extracted.
        plots (bool): If True will show plots, similar to a debugging mode.

    Returns:
        nccd (object): Instance of ccdproc.CCDData that contains only the region
        extracted from the full image. The header is updated with a new HISTORY
        keyword that contain the region of the original image extracted.
        model (object): Instance of astropy.modeling.Model with an updated mean
        to match the new center in pixel units.

    """

    spatial_length, dispersion_length = ccd.data.shape

    mean = model.mean.value
    stddev = model.stddev.value
    extract_width = n_sigma_extract // 2 * stddev

    low_lim = np.max([0, int(mean - extract_width)])
    hig_lim = np.min([int(mean + extract_width), spatial_length])

    nccd = ccd.copy()
    nccd.data = ccd.data[low_lim:hig_lim, :]
    nccd.header['HISTORY'] = 'Subsection of CCD [{:d}:{:d}, :]'.format(low_lim,
                                                                       hig_lim)
    model.mean.value = extract_width

    if plots:
        plt.imshow(ccd.data)
        plt.axhspan(low_lim, hig_lim, color='r', alpha=0.2)
        plt.show()

    return nccd, model


def add_wcs_keys(header):
    """Adds generic keyword to the header
    Linear wavelength solutions require a set of standard fits keywords. Later on they will be updated accordingly
    The main goal of putting them here is to have consistent and nicely ordered headers

    Args:
        header (object): New header without WCS entries

    Returns:
        header (object): Modified header

    """
    try:
        header['BANDID1'] = 'spectrum - background none, weights none, clean no'
        header['APNUM1'] = '1 1 0 0'
        header['WCSDIM'] = 1
        header['CTYPE1'] = 'LINEAR'
        header['CRVAL1'] = 1
        header['CRPIX1'] = 1
        header['CDELT1'] = 1
        header['CD1_1'] = 1
        header['LTM1_1'] = 1
        header['WAT0_001'] = 'system=equispec'
        header['WAT1_001'] = 'wtype=linear label=Wavelength units=angstroms'
        header['DC-FLAG'] = 0
        header['DCLOG1'] = 'REFSPEC1 = non set'
        return header
    except TypeError as err:
        log.error("Can't add wcs keywords to header")
        log.debug(err)
