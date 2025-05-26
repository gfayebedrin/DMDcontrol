clc

% --- Prepare image -------------------------------------------------------

% The image should be 1024 x 768

Img = imread('C:\Users\LJP\Documents\Science\Projects\Braintegration\Sample_Images\skull.png');

% --- Grey level image
X = meshgrid(1:size(Img,2), 1:size(Img,1));
tmp = double(Img(:,:,1)).*X;
Img = uint8(tmp/max(tmp(:))*255)';

warning off
imshow(Img')
warning on

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
A.load(Img, 'grey');

% Start/stop projection
A.start();
pause
A.stop();

% Display the image for a given amount of time (in seconds)
% A.play(0.01);