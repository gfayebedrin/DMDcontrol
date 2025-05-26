clc

% --- Prepare image sequence ----------------------------------------------

% The sequence should be 1024 x 768 x n

if ~exist('Seq', 'var')
    
    fprintf('Creating image sequence ...'); tic
    
    Img = imread('C:\Users\LJP\Documents\Science\Projects\Braintegration\Sample_Images\skull.png');
    Img = uint8(((Img(:,:,1)')<128)*255);
    
    % First image
    Seq = Img;
      
    % Create sequence
    for i = 1:359
        Seq(:,:,end+1) = imrotate(Img, i, 'nearest', 'crop');
    end
    
    fprintf(' %.02f sec\n', toc);
    
end

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

% Load the sequence
A.load(Seq);

% Set the display rate (framerate in Hz)
A.rate(360);

% Warning
%   A sequence cannot be interrupted once it's started. That means that the
%   effective exposure time can only be an integer multiple of the number 
%   of images divided by the framerate. As a side effect, if the program
%   tries to stop the exposure in the middle of a sequence then the 
%   exposure will stop only when the sequence is finished. Thus the 
%   exposure time can be significantly higher than expected if there are
%   many images and the framerate is low.

% Start/stop projection
A.start();
pause 
A.stop();

% Play the sequence for a given amount of time (in seconds)
% A.play(1);