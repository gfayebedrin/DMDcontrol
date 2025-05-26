clc

% --- Prepare image -------------------------------------------------------

% The image should be 1024 x 768

Img = imread('C:\Users\LJP\Documents\Science\Projects\Braintegration\Sample_Images\skull.png');

% --- Black pattern
% Img = uint8(((Img(:,:,1)')>128)*255);

% --- White pattern
Img = uint8(((Img(:,:,1)')<128)*255);

% --- DMD control ---------------------------------------------------------

% Warning
%   When the DMD device is not allocated it rests in an idle state where 
%   the mirrors can take any position. The shutter must thus be off before 
%   device allocation (at object instantiation) and each time the device is
%   de-allocated (object destruction, e.g. with clear).

% De-allocate existing device (if any)
clear A

% Create a DMD device
A = DMD.Alp;

% Load the image

A.load(Img);

% Start/stop projection
%A.start();
% A.stop();

% Display the image for a given amount of time (in seconds)
A.play(1);