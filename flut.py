import numpy as np
from src.hardware.ALP4 import *
import ctypes as ct

# Load the Vialux .dll
DMD = ALP4(libDir=r"C:\Program Files\ALP-4.3\ALP-4.3 API")
# Initialize the device
DMD.Initialize()

# Binary amplitude image (0 or 1)
bitDepth = 1

imgBlack = np.zeros([DMD.nSizeY, DMD.nSizeX])
imgWhite = np.ones([DMD.nSizeY, DMD.nSizeX]) * (2**8 - 1)
imgStripe = np.zeros([DMD.nSizeY, DMD.nSizeX])
imgStripe[:, : DMD.nSizeX // 2] = 1

imgSeq = np.concatenate([imgBlack.ravel(), imgWhite.ravel(), imgStripe.ravel()])

# Allocate the onboard memory for the image sequence
DMD.SeqAlloc(nbImg=2, bitDepth=bitDepth)
# Send the image sequence as a 1D list/array/numpy array
DMD.SeqPut(imgData=imgSeq)
# Set image rate to 5 Hz
DMD.SetTiming(pictureTime=200_000)

# Linear sequence display
DMD.Run()
input("Press Enter to stop...")
DMD.Halt()


# FLUT display

frame_numbers = [0, 2, 1, 2]

flut = tFlutWrite(
    nOffset=ct.c_long(0),
    nSize=ct.c_long(len(frame_numbers)),
    FrameNumbers=(ct.c_ulong * 4096)(*frame_numbers),
)

DMD.SeqControl(ALP_FLUT_MODE, ALP_FLUT_9BIT)
DMD.SeqControl(ALP_FLUT_ENTRIES9, len(frame_numbers))
DMD.ProjControlEx(ALP_FLUT_WRITE_9BIT, ct.byref(flut))

DMD.Run()
input("Press Enter to stop...")
DMD.Halt()


# Free the sequence from the onboard memory
DMD.FreeSeq()
# De-allocate the device
DMD.Free()
