from pyexplorex import pyexplorex

# create object
handler = pyexplorex.PyExploreX()

def test_amp_cb_ch1(scan_rate, point_count, data_ptr, size):
    print("[ch1] test amp recv data:", data_ptr[0:150])
    pass


def test_phase_cb_ch1(scan_rate, point_count, data_ptr, size):
    print("[ch1] test phase recv data:", data_ptr[0:150])
    pass

def test_amp_cb_ch2(scan_rate, point_count, data_ptr, size):
    print("[ch2] test amp recv data:", data_ptr[0:150])
    pass


def test_phase_cb_ch2(scan_rate, point_count, data_ptr, size):
    print("[ch2] test phase recv data:", data_ptr[0:150])
    pass

# Start a collector
print("version: ", handler.version())

# Start a collector
handler.create()
# Set collection parameters
handler.setParams(aom=pyexplorex.Aom.Aom80, scanRate=pyexplorex.ScanRate.Rate10, mode=pyexplorex.Mode.CoherentSuppression, pulseWidth=100, scaleDown=3)
# Set memory block size
handler.setBlockCount()
# Set channel 1 amplitude data callback
handler.setAmpDataCallback(test_amp_cb_ch1)
# Set channel 1 phase data callback
handler.setPhaseDataCallback(test_phase_cb_ch1)
# Set channel 2 amplitude data callback
handler.setAmpDataCallbackCh2(test_amp_cb_ch2)
# Set channel 2 phase data callback
handler.setPhaseDataCallbackCh2(test_phase_cb_ch2)

# Open the collection card
open_ret = handler.open()
if (open_ret != 0) :
    print("fail to open, ret:", open_ret)
else:
    print("open success")
    # Start collecting
    start_ret = handler.start()

    if (open_ret != 0) :
        print("fail to start, ret:", open_ret)
    else:
        user_input = input("输入任意字符结束...")
    # Stop collecting
    handler.stop()

# Destroy the collector
handler.destroy()