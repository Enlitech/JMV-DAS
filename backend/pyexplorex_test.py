import numpy as np
from . import pyexplorex

handler = pyexplorex.PyExploreX()

amp_ch1_blocks = []
phase_ch1_blocks = []
amp_ch2_blocks = []
phase_ch2_blocks = []


def parse_block(scan_rate, point_count, data_ptr, size):

    cb_lines = int(scan_rate)
    point_count = int(point_count)
    size = int(size)

    raw = bytes(data_ptr[:size])

    arr = np.frombuffer(raw, dtype=np.float32)

    total = arr.size

    if cb_lines * point_count <= total:
        num_lines = cb_lines
    else:
        num_lines = total // point_count

    arr = arr[:num_lines * point_count]

    block = arr.reshape((num_lines, point_count))

    return block


def test_amp_cb_ch1(scan_rate, point_count, data_ptr, size):

    block = parse_block(scan_rate, point_count, data_ptr, size)

    amp_ch1_blocks.append(block)

    print("[ch1 amp] block:", block.shape)


def test_phase_cb_ch1(scan_rate, point_count, data_ptr, size):

    block = parse_block(scan_rate, point_count, data_ptr, size)

    phase_ch1_blocks.append(block)

    print("[ch1 phase] block:", block.shape)


def test_amp_cb_ch2(scan_rate, point_count, data_ptr, size):

    block = parse_block(scan_rate, point_count, data_ptr, size)

    amp_ch2_blocks.append(block)

    print("[ch2 amp] block:", block.shape)


def test_phase_cb_ch2(scan_rate, point_count, data_ptr, size):

    block = parse_block(scan_rate, point_count, data_ptr, size)

    phase_ch2_blocks.append(block)

    print("[ch2 phase] block:", block.shape)


print("version:", handler.version())

handler.create()

handler.setParams(
    aom=pyexplorex.Aom.Aom80,
    scanRate=pyexplorex.ScanRate.Rate10,
    mode=pyexplorex.Mode.CoherentSuppression,
    pulseWidth=100,
    scaleDown=3
)

handler.setBlockCount()

handler.setAmpDataCallback(test_amp_cb_ch1)
handler.setPhaseDataCallback(test_phase_cb_ch1)
handler.setAmpDataCallbackCh2(test_amp_cb_ch2)
handler.setPhaseDataCallbackCh2(test_phase_cb_ch2)


open_ret = handler.open()

if open_ret != 0:
    print("fail to open:", open_ret)

else:

    print("open success")

    start_ret = handler.start()

    if start_ret != 0:
        print("fail to start:", start_ret)

    else:
        input("输入任意字符结束采集...")

    handler.stop()

handler.destroy()

print("saving data...")

if amp_ch1_blocks:
    amp_ch1 = np.concatenate(amp_ch1_blocks, axis=0)
    np.save("amp_ch1.npy", amp_ch1)

if phase_ch1_blocks:
    phase_ch1 = np.concatenate(phase_ch1_blocks, axis=0)
    np.save("phase_ch1.npy", phase_ch1)

if amp_ch2_blocks:
    amp_ch2 = np.concatenate(amp_ch2_blocks, axis=0)
    np.save("amp_ch2.npy", amp_ch2)

if phase_ch2_blocks:
    phase_ch2 = np.concatenate(phase_ch2_blocks, axis=0)
    np.save("phase_ch2.npy", phase_ch2)

print("done.")