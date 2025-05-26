% calibrate
im_dir='S:\calibrate\';


ch=uint8(255*(checkerboard(64,8,6)<0.5));
A.load(j-j);
A.start();
x=input('enter when image taken');
filenames=dir([im_dir '*.tif']);
im_wf=imread([im_dir filenames(end).name]);
A.stop();
A.load(ch);
A.start();
x=input('enter when image taken');
filenames=dir([im_dir '*.tif']);
im_ch=imread([im_dir filenames(end).name]);
A.stop();
im_norm=double(im_ch)./im_wf;

tform = imregtform(255-ch, im_norm, 'similarity',optimizer,metric);


