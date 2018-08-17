# 2Dscan
Simple Python app synchronizing a 2D scan of XY stages with a signal measurement.
This app was developed to measure the intensity distribution of a laser beam, by simply moving (scanning) a photodetector (reverse-biased photodiode with a small pin-hole aperture) mounted on a X-Y translation stage. The translation stages are controlled by an Arduino board (with a CNC shield) running grbl g-code interpreter, and the signal is sampled/measured using our DataSpider board.
The program has a GUI to select and enter parameters such as COM p orts for the Arduino-grbl and the DataSpider data-acquisition board.
