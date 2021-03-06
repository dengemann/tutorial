"""
Validation and conversion utilities.
"""
# Author: Gael Varoquaux, Alexandre Abraham
# License: simplified BSD


import collections
import warnings

import nibabel
import numpy as np
from scipy import ndimage
from sklearn.externals.joblib import Memory


###############################################################################
# Operating on connect component
###############################################################################

def largest_connected_component(volume):
    """Return the largest connected component of a 3D array.

    Parameters
    -----------
    volume: 3D boolean array
        3D array indicating a volume.

    Returns
    --------
    volume: 3D boolean array
        3D array with only one connected component.
    """
    # We use asarray to be able to work with masked arrays.
    volume = np.asarray(volume)
    labels, label_nb = ndimage.label(volume)
    if not label_nb:
        raise ValueError('No non-zero values: no connected components')
    if label_nb == 1:
        return volume.astype(np.bool)
    label_count = np.bincount(labels.ravel())
    # discard the 0 label
    label_count[0] = 0
    return labels == label_count.argmax()


###############################################################################
# Niimg related operations
###############################################################################

def is_a_niimg(object):
    """ Check for get_data and get_affine method in an object

    Parameters
    ----------
    object: unknown object
        Tested object

    Returns
    -------
    True if get_data and get_affine methods are present and callable,
    False otherwise.
    """

    # We use a try/except here because this is the way hasattr works
    try:
        get_data = getattr(object, "get_data")
        get_affine = getattr(object, "get_affine")
        return callable(get_data) and callable(get_affine)
    except AttributeError:
        return False


def _get_shape(niimg):
    # Use the fact that Nifti1Image has a shape attribute that is
    # faster than loading the data from disk
    if hasattr(niimg, 'shape'):
        shape = niimg.shape
    else:
        shape = niimg.get_data().shape
    return shape


def _repr_niimgs(niimgs):
    """ Pretty printing of niimg or niimgs.
    """
    if isinstance(niimgs, basestring):
        return niimgs
    if isinstance(niimgs, collections.Iterable):
        return '[%s]' % ', '.join(_repr_niimgs(niimg) for niimg in niimgs)
    # Nibabel objects have a 'get_filename'
    try:
        return "%s('%s')" % (niimgs.__class__.__name__,
                             niimgs.get_filename())
    except:
        pass
    return repr(niimgs)


def check_niimg(niimg):
    """ Check that an object is a niimg and load it if necessary

    Parameters
    ----------
    niimg: string or object
        If niimg is a string, consider it as a path to Nifti image and
        call nibabel.load on it. If it is an object, check if get_data
        and get_affine methods are present, raise an Exception otherwise.

    Returns
    -------
    result: nifti-like
       result can be nibabel.Nifti1Image or the input, as-is. It is guaranteed
       that the returned object has get_data() and get_affine() methods.

    Notes
    -----
    In Nisl, special care has been taken to make image manipulation easy. This
    method is a kind of pre-requisite for any data processing method in Nisl as
    it checks if data has a correct format and loads it if necessary.

    Its application is idempotent.
    """

    if isinstance(niimg, basestring):
        # data is a filename, we load it
        result = nibabel.load(niimg)
    else:
        # it is an object, it should have get_data and get_affine methods
        if not is_a_niimg(niimg):
            raise TypeError("Given data does not expose"
                            " get_data or get_affine methods")
        result = niimg
    return result


def concat_niimgs(niimgs):
    """ Concatenate a list of niimgs

    Parameters
    ----------
    niimgs: array of niimgs
        List of niimgs to concatenate. Can be paths to Nifti files or numpy
        matrices.

    Returns
    -------
    A single niimg
    """

    data = []
    first_niimg = check_niimg(iter(niimgs).next())
    affine = first_niimg.get_affine()
    for index, iter_niimg in enumerate(niimgs):
        niimg = check_niimg(iter_niimg)
        if not np.array_equal(niimg.get_affine(), affine):
            s_error = ""
            if (isinstance(iter_niimg, basestring)):
                i_error = "image " + iter_niimg
            else:
                i_error = "image #" + str(index)

            raise ValueError("Affine of %s%s is different"
                             " from reference affine"
                             "\nReference affine:\n%s\n"
                             "Wrong affine:\n%s"
                             % (i_error, s_error,
                             repr(affine), repr(niimg.get_affine())))
        this_data = niimg.get_data()
        if len(this_data.shape) == 3:
            this_data = this_data[..., np.newaxis]
        data.append(this_data)
    data = np.concatenate(data, axis=-1)
    return nibabel.Nifti1Image(data, affine)


def check_niimgs(niimgs, accept_3d=False):
    """ Check that an object is a list of niimg and load it if necessary

    Parameters
    ----------
    niimgs: (list of)* string or object
        If niimgs is a list, checks if data is really 4D. Then, considering
        that it is a list of niimg and load them one by one.
        If niimg is a string, consider it as a path to Nifti image and
        call nibabel.load on it. If it is an object, check if get_data
        and get_affine methods are present, raise an Exception otherwise.

    Returns
    -------
    A list of nifti-like object (for the moment, nibabel.Nifti1Image)

    Notes
    -----
    This application is the pendant of check_niimg for niimages with a session
    level.

    Its application is idempotent.
    """
    # Initialization:
    # If given data is a list, we count the number of levels to check
    # dimensionality and make a consistent error message.
    depth = 0
    first_img = niimgs
    if accept_3d and (isinstance(first_img, basestring)
                      or not isinstance(first_img, collections.Iterable)):
        niimg = check_niimg(niimgs)
        if len(_get_shape(niimg)) == 3:
            niimg = nibabel.Nifti1Image(niimg.get_data()[..., np.newaxis],
                                        niimg.get_affine())
        return niimg

    # Use hasattr() instead of isinstance to workaround a Python 2.6/2.7 bug
    # See http://bugs.python.org/issue7624
    while hasattr(first_img, "__iter__") \
            and not isinstance(first_img, basestring):
        first_img = iter(first_img).next()
        depth += 1

    # First image is supposed to be a path or a Nifti-like element
    first_img = check_niimg(first_img)

    # Check dimension and depth
    dim = len(_get_shape(first_img))

    if (dim + depth) != 4:
        # Detailed error message that tells exactly the user what
        # was provided and what should have been provided.
        raise TypeError("Data must be either a 4D Nifti image or a"
                        " list of 3D Nifti images. You provided a %s%dD"
                        " image(s)." % ('list of ' * depth, dim))

    # Now, we load data as we know its format
    if dim == 4:
        niimg = check_niimg(niimgs)
    else:
        niimg = concat_niimgs(niimgs)
    return niimg


###############################################################################
### Caching
###############################################################################

class CacheMixin(object):
    """Mixin to add caching to a class.

    This class is a thin layer on top of joblib.Memory, that mainly adds a
    "caching level", similar to a "log level".

    Usage: to cache the results of a method, wrap it in self._cache()
    defined by this class. Caching is performed only if the user-specified
    cache level (self._memory_level) is greater than the value given as a
    parameter to self._cache(). See _cache() documentation for details.
    """

    def _cache(self, func, memory_level=1, **kwargs):
        """ Return a joblib.Memory object if necessary.

        The memory_level determines the level above which the wrapped
        function output is cached. By specifying a numeric value for
        this level, the user can to control the amount of cache memory
        used. This function will cache the function call or not
        depending on the cache level.

        Parameters
        ----------
        func: python function
            The function which output is to be cached.

        memory_level: integer
            The memory_level from which caching must be enabled for the wrapped
            function.

        Returns
        -------
        Either the original function, if there is no need to cache it (because
        the requested level is lower than the value given to _cache()) or a
        joblib.Memory object that wraps the function func.
        """

        # Creates attributes if they don't exist
        # This is to make creating them in __init__() optional.
        if not hasattr(self, "memory_level"):
            self.memory_level = 0
        if not hasattr(self, "memory"):
            self.memory = Memory(cachedir=None)

        # If cache level is 0 but a memory object has been provided, set
        # memory_level to 1 with a warning.
        if self.memory_level == 0:
            if (isinstance(self.memory, basestring)
                    or self.memory.cachedir is not None):
                warnings.warn("memory_level is currently set to 0 but "
                              "a Memory object has been provided. "
                              "Setting memory_level to 1.")
                self.memory_level = 1

        if self.memory_level < memory_level:
            mem = Memory(cachedir=None)
            return mem.cache(func, **kwargs)
        else:
            memory = self.memory
            if isinstance(memory, basestring):
                memory = Memory(cachedir=memory)
            if not isinstance(memory, Memory):
                raise TypeError("'memory' argument must be a string or a "
                                "joblib.Memory object.")
            if memory.cachedir is None:
                warnings.warn("Caching has been enabled (memory_level = %d) but no"
                              " Memory object or path has been provided (parameter"
                              " memory). Caching deactivated for function %s." %
                              (self.memory_level, func.func_name))
            return memory.cache(func, **kwargs)
