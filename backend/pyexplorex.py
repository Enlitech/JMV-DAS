import ctypes
from enum import Enum
import os

class Aom(Enum):
    """Acousto-optic modulator."""

    Aom80 = 0 #: 80M
    """80M."""
    
    Aom200 = 1 #: 200M
    """200M."""

class ScanRate(Enum):
    """Repeat scanning frequency"""

    Rate1 = 0 # 1k
    """1k"""
    Rate2 = 1 # 2k
    """2k"""
    Rate4 = 2 # 4k
    """4k"""
    Rate10 = 3 # 10K
    """10k"""

class Mode(Enum):
    """Demodulation mode"""
    
    CoherentSuppression = 0 # 10K
    """Coherent suppression mode"""
    PolarizationSuppression = 1 # 4k
    """Polarization suppression mode"""
    CoherentPolarizationSuppression = 2 # 2k
    """Coherent Polarization Suppression Mode"""

dll_dir = __file__.replace('pyexplorex.py', '')

# Set DLL path
if os.name == "nt":
    os.add_dll_directory(f'{dll_dir}win64')
    # Load shared library
    lib = ctypes.CDLL('explorex_c.dll')
elif os.name == "posix":
    os.environ['LD_LIBRARY_PATH'] += f'{dll_dir}linux'
    lib = ctypes.cdll.LoadLibrary(f'{dll_dir}linux/libexplorex_c.so')
    pass

# Define Function Prototype
# Create reference
lib.exapi_version.argtypes = []
lib.exapi_version.restype = ctypes.c_char_p
# Create reference
lib.exapi_create.argtypes = []
lib.exapi_create.restype = ctypes.c_void_p
# Destroy references
lib.exapi_destroy.argtypes = []
lib.exapi_destroy.restype = ctypes.c_void_p
# Set collection configuration
lib.exapi_set_params.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
lib.exapi_set_params.restype = ctypes.c_void_p
# Set collection cache configuration
lib.exapi_set_block_count.argtypes = [ctypes.c_int,ctypes.c_int]
lib.exapi_set_block_count.restype = ctypes.c_void_p
# Amp/phase data callback
DataCallbackType = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_char), ctypes.c_ulong)

# Open the collection card
lib.exapi_open.argtypes = []
lib.exapi_open.restype = ctypes.c_int
# Start collecting
lib.exapi_start.argtypes = []
lib.exapi_start.restype = ctypes.c_int
# Stop collecting
lib.exapi_stop.argtypes = []
lib.exapi_stop.restype = ctypes.c_int

# Define functions related to GIL
PyGILState_Ensure = ctypes.pythonapi.PyGILState_Ensure
PyGILState_Release = ctypes.pythonapi.PyGILState_Release
PyGILState_Ensure.restype = ctypes.c_int
PyGILState_Release.argtypes = [ctypes.c_int]

class PyExploreX(object):
    """Read the collection card py tool class"""
    
    def __init__(self):
        super(PyExploreX, self).__init__()
        self.ampCb = None
        self.phaseCb = None
        self._c_amp_data_callback = None
        self._c_phase_data_callback = None
        self.ampCbCh2 = None
        self.phaseCbCh2 = None
        self._c_amp_data_callback_ch2 = None
        self._c_phase_data_callback_ch2 = None
        pass

    def _amp_data_cb(self, scan_rate, point_count, data_ptr, size):
        try:
            if self.g_ampCb != None:
                self.g_ampCb(scan_rate, point_count, data_ptr, size)
        except Exception as e:
            print(f"Error in Python callback: {e}")
        pass

    def _phase_data_cb(self, scan_rate, point_count, data_ptr, size):
        try:
            if self.g_phaseCb != None:
                self.g_phaseCb(scan_rate, point_count, data_ptr, size)
        except Exception as e:
            print(f"Error in Python callback: {e}")
        pass
    
    def _amp_data_cb_ch2(self, scan_rate, point_count, data_ptr, size):
        try:
            if self.g_ampCbCh2 != None:
                self.g_ampCbCh2(scan_rate, point_count, data_ptr, size)
        except Exception as e:
            print(f"Error in Python callback: {e}")
        pass

    def _phase_data_cb_ch2(self, scan_rate, point_count, data_ptr, size):
        try:
            if self.g_phaseCbCh2 != None:
                self.g_phaseCbCh2(scan_rate, point_count, data_ptr, size)
        except Exception as e:
            print(f"Error in Python callback: {e}")
        pass

    def version(self):
        """VERSION"""

        return lib.exapi_version()

    def create(self):
        """Create a collection card to read references"""

        lib.exapi_create()
        print("create instance")
        pass

    def destroy(self):
        """Destroy the collection card and read the reference"""

        lib.exapi_destroy()
        print("destroy instance")
        pass

    def open(self) -> int: 
        """Open the collection card"""

        ret = lib.exapi_open()
        print("open daq, ret: %d" % ret)
        return ret

    def setAmpDataCallback(self, cb):
        """Set channel 1 amplitude data callback"""

        self.g_ampCb = cb
        self._c_amp_data_callback = DataCallbackType(self._amp_data_cb)
        lib.exapi_set_amp_data_callback(self._c_amp_data_callback)
        pass

    def setPhaseDataCallback(self, cb):
        """Set channel 1 phase data callback"""
        
        self.g_phaseCb = cb
        self._c_phase_data_callback = DataCallbackType(self._phase_data_cb)
        lib.exapi_set_phase_data_callback(self._c_phase_data_callback)
        pass
    

    def setAmpDataCallbackCh2(self, cb):
        """Set channel 2 amplitude data callback"""

        self.g_ampCbCh2 = cb
        self._c_amp_data_callback_ch2 = DataCallbackType(self._amp_data_cb_ch2)
        lib.exapi_set_channel2_amp_data_callback(self._c_amp_data_callback_ch2)
        pass

    def setPhaseDataCallbackCh2(self, cb):
        """Set channel 2 phase data callback"""
        
        self.g_phaseCbCh2 = cb
        self._c_phase_data_callback_ch2 = DataCallbackType(self._phase_data_cb_ch2)
        lib.exapi_set_channel2_phase_data_callback(self._c_phase_data_callback_ch2)
        pass

    def start(self) -> int:
        """Start collecting.
        
        Returns:
        
        int: Start collecting status codes.
        """

        ret = lib.exapi_start()
        print("start daq, ret: %d" % ret)
        return ret

    def stop(self)-> int:
        """Stop collecting.
        
        Returns:
        
        int: Stop collecting status codes.
        """

        ret = lib.exapi_stop()
        print("stop daq, ret: %d" % ret)
        return ret

    def setParams(self,
        aom: Aom = Aom.Aom80,
        scanRate: ScanRate = ScanRate.Rate10,
        mode: Mode = Mode.CoherentSuppression,
        pulseWidth: int = 100,
        scaleDown: int = 2):
        """Set collection parameters.
        
        Parameters:
        
        aom (Aom): Acousto optic modulator.

        scanRate (ScanRate): Repeat scanning frequency.

        mode (Mode): Demodulation mode.

        pulseWidth (PulseWidth): Position width.

        scaleDown (ScaleDown): Down conversion coefficient.
        """

        lib.exapi_set_params(aom.value, scanRate.value, mode.value, pulseWidth, scaleDown)
        print("set daq params done")
        pass

    def setBlockCount(self, readBlockCnt: int = 3, cacheBlockCnt: int = 3):
        """Set the number of data blocks to be collected.
        
        Parameters:
        
        readBlockCnt (int): Read the number of cache blocks, default is 3.
        
        cacheBlockCnt (int): Number of data callback cache blocks, default 3.
        
        """

        lib.exapi_set_block_count(readBlockCnt, cacheBlockCnt)
        print("set block count done")
        pass

def test_amp_cb_ch1(scan_rate, point_count, data_ptr, size):
    print("test amp Received data:", data_ptr[0:150])
    pass

def test_amp_cb_ch2(scan_rate, point_count, data_ptr, size):
    print("test amp Received data:", data_ptr[0:150])
    pass

def test_phase_cb_ch1(scan_rate, point_count, data_ptr, size):
    print("test phase Received data:", data_ptr[0:150])
    pass

def test_phase_cb_ch2(scan_rate, point_count, data_ptr, size):
    print("test phase Received data:", data_ptr[0:150])
    pass

def test():
    # Create object
    handler = PyExploreX()
    
    # Start a collector
    handler.create()
    # Set collection parameters
    handler.setParams(scaleDown=3)
    # Set memory block size
    handler.setBlockCount()
    # Set channel 1 amplitude data callback
    handler.setAmpDataCallback(test_amp_cb_ch1)
    # Set channel 1 phase data callback
    handler.setPhaseDataCallback(test_phase_cb_ch1)

    # Open the collection card
    open_ret = handler.open()
    if (open_ret != 0) :
        print("fail to open, ret:", open_ret)
        return

    print("open success")

    # Start collecting
    start_ret = handler.start()

    if (open_ret != 0) :
        print("fail to start, ret:", open_ret)
        return

    user_input = input("Enter any character to end...")

    # Stop collecting
    handler.stop()
    # Destroy the collector
    handler.destroy()
    pass
