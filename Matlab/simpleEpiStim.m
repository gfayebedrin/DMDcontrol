%% Reset DMD
clear A

%% Alloc DMD
A = DMD.Alp;

%% Load Mask
A.stop();
pause(0.2);
A.load(Mask);
A.start;
%% Full illumination
Img = 255 * uint8(zeros(1024,768));
A.stop();
pause(0.2);

A.load(Img);
A.start();

%% Full dark
Img = 255 * uint8(ones(1024,768));
A.stop();
pause(0.2);
A.load(Img);
A.start();

%% 1/2 illumination
Img = 255 * uint8(ones(1024,768));
Img(512:end,:)=0;
A.stop();
pause(0.2);
A.load(Img);
A.start();
%% Full square illumination
Img = 255 * uint8(ones(1024,768));
Img(128:end-128,:)=0;
A.stop();
pause(0.2);
A.load(Img);
A.start();
%% Show central square

nH = 500;     % size of square on the hamamatsu image

n = min([nH*201/(435*2) 766/2]);
Img = 255 * uint8(ones(1024,768));
Img(512-n:512+n,384-n:384+n)=0;
A.stop();
pause(0.2);
A.load(Img);
A.start();

%% Show central rectangle

heightH = 480;     % height on the hamamatsu image
widthH = 1200;      % width on the hamamatsu image

height = min([heightH*201/(435*2) 511]);
width = min([widthH*201/(435*2) 383]);
Img = 255 * uint8(ones(1024,768));
Img(512-width:512+width,384-height:384+height)=0;
A.stop();
pause(0.2);
A.load(Img);
A.start();



%% Stop
A.stop();