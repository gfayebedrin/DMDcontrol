classdef epiStimulationOfflineSequence < handle
% Shows a sequence of regions of stimulation from epi-fluorescence arm
%
% Needs the handle to a live occurence of Lighsheet
% Select in the offline image (saved on disk) a sequence 
% of regions of interest to be illuminated by the DMD setup

    properties
        
        Folder = 'C:\Users\LJP\Documents\Thomas\Dmd Cal test\'
        CameraFigure            % Main figure, contains the offline camera view
        CameraFigureFlag = 0;    % Is the main figure already loaded?
        ControlsDMD             % Figure for DMD controls               
        ImageCamera             % Image read from disk
        ImageCameraName         % Name for current image read from disk
        HamamatsuMask           % Mask for Hamamatsu image
        DmdDevice               % DMD Object
        Mask                    % Mask to be sent to the DMD
        MaskSequence=uint8([]); % Array of masks to be displayed
        CurrentMaskNb = 0       % Currently displayed mask number
        Drawing                 % ROI drawn on image where the light should shine
        AddToMaskFlag           % Add drawing to mask (1) or create new mask (0)
        AutoUploadFlag          % Automatic upload after drawing (1, Default) or not (0)
        DmdPosition             % [left bottom width height] of DMD  square zone on Hamamatsu image
        
    end
    
    methods
        
        function app = epiStimulationOfflineSequence(LightSheetHandle)
                                          
            app.uiMaker();
            
            app.DmdDevice = DMD.Alp;
            
            app.resetMask();
            app.uploadMask();
            
            addlistener(LightSheetHandle,'DMDinit',@app.initDmdSequence);
            addlistener(LightSheetHandle,'DMDtrigNext',@app.showNextMask);
            

        end
        
        function closeApp(app, hObjects, eventData)
            % Closes the app
            delete(app.CameraFigure);
            delete(app.ControlsDMD);
            delete(app.DmdDevice);
        end        
        
        function uiMaker(app, hObjects, eventData)
            % Constructs the various windows of the user interface
                    
            %------------------------------------------------------------%
            % Controls for DMD mask
            %------------------------------------------------------------%
            
            app.ControlsDMD = figure('Toolbar','none',...
                 'Menubar', 'none',...
                 'NumberTitle','Off',...
                 'Name','Controles DMD',...
                 'OuterPosition', [750 30 440 180],...
                 'CloseRequestFcn',@app.closeApp) ;
            
            % First Column ----------------------------------------------%
            uicontrol(app.ControlsDMD,'String', 'Draw Freehand',...
                'Callback', @app.drawFreehand,...
                'Position',[5 110 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Draw Rectangle',...
                'Callback', @app.drawRectangle,...
                'Position',[5 75 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Draw Ellipse',...
                'Callback', @app.drawEllipse,...
                'Position',[5 40 100 30]);
            app.AddToMaskFlag = uicontrol(app.ControlsDMD,...
                'Style', 'togglebutton',...
                'String', 'Add to mask',...
                'Min',0 ,'Max',1,...
                'Position',[5 5 100 30]);
            
            % Second Column ---------------------------------------------%
            app.AutoUploadFlag = uicontrol(app.ControlsDMD,...
                'Style', 'togglebutton',...
                'String', 'Auto Upload',...
                'Min',0 ,'Max',1,...
                'Value', 1,...
                'Position',[110 110 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Reset Mask',...
                'Callback', @app.resetMask,...
                'Position',[110 75 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Upload Mask',...
                'Callback', @app.uploadMask,...
                'Position',[110 40 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Adjust Contrast',...
                'Callback', @app.adjustContrast,...
                'Position',[110 5 100 30]);
            
            % Third Column ----------------------------------------------%
            uicontrol(app.ControlsDMD,'String', 'Update Image',...
                'Callback', @app.updateImage,...
                'Position',[215 110 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Save Mask/Image',...
                'Callback', @app.saveMaskedImage,...
                'Position',[215 75 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Show Cal. Mask',...
                'Callback', @app.calibrationMask,...
                'Position',[215 40 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Calibrate DMD',...
                'Callback', @app.calibrateDMD,...
                'Position',[215 5 100 30]);
            
            % Fourth Column ---------------------------------------------%
            uicontrol(app.ControlsDMD,'String', 'Change Folder',...
                'Callback', @app.changeFolder,...
                'Position',[320 110 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Add To Seq.',...
                'Callback', @app.addMaskToSequence,...
                'Position',[320 75 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Reset Seq.',...
                'Callback', @app.resetSequence,...
                'Position',[320 40 100 30]);
            uicontrol(app.ControlsDMD,'String', 'Show Next Mask',...
                'Callback', @app.showNextMask,...
                'Position',[320 2 100 30]);
        end
        
        function changeFolder(app, hObjects, eventData)
            app.Folder = uigetdir('C:\Users\LJP\Documents\', 'Select Folder');           
        end
               
        function updateImage(app, hObjects, eventData)
            % Displays the latest tif image in the app.Folder
            
            filesTemp = dir([app.Folder '*.tif']);
            filesDate = zeros(1,length(filesTemp));
            for i = 1:length(filesTemp)
                filesDate(i) = filesTemp(i).datenum;
            end
            [temp tempIndex]=max(filesDate);
            app.ImageCameraName = filesTemp(tempIndex).name;
            app.ImageCamera = imread([app.Folder app.ImageCameraName]);
            if ~app.CameraFigureFlag
                app.CameraFigure = figure('CloseRequestFcn',@app.closeApp);
                app.CameraFigureFlag = 1;                
            end
            figure(app.CameraFigure)
            imshow(app.ImageCamera);
        end
        
        function adjustContrast(app, hObjects, eventData)
            imcontrast(app.CameraFigure);                        
        end
        
        function calibrationMask(app, hObjects, eventData)
            app.resetMask();
            app.Mask(128:end-128,:) = 0; % Full Height Square (768x768)
%             app.Mask(263:262+499, 133:132+499) = 0;  % 500 x 500 square
            app.uploadMask();

        end    
        
        function calibrateDMD(app, hObjects, eventData)
            if ~app.CameraFigureFlag
                app.updateImage();
                app.CameraFigureFlag = 1;
            end            
            app.DmdPosition = getrect(app.CameraFigure.CurrentAxes);
            app.resetMask();
            app.uploadMask();
        end
        
        function drawFreehand(app, hObjects, eventData)
            if ~app.CameraFigureFlag
                app.updateImage();
                app.CameraFigureFlag = 1;
            end
            app.Drawing = imfreehand(app.CameraFigure.CurrentAxes);
            app.createDmdMask();
            if app.AutoUploadFlag.Value
                app.uploadMask();
            end
        end
      
        function drawRectangle(app, hObjects, eventData)
            if ~app.CameraFigureFlag
                app.updateImage();
                app.CameraFigureFlag = 1;
            end
            app.Drawing = imrect(app.CameraFigure.CurrentAxes);
            app.createDmdMask();
            if app.AutoUploadFlag.Value
                app.uploadMask();
            end
        end
        
        function drawEllipse(app, hObjects, eventData)
            if ~app.CameraFigureFlag
                app.updateImage();
                app.CameraFigureFlag = 1;
            end
            app.Drawing = imellipse(app.CameraFigure.CurrentAxes);
            app.createDmdMask();
            if app.AutoUploadFlag.Value
                app.uploadMask();
            end
        end
              
        function createDmdMask(app, hObjects, eventData)
            % Creates new mask or adds to existing mask

            tempMask = app.Drawing.createMask();
            M = tempMask';
            
% full height square case           
            M(:,1:round(app.DmdPosition(2))) = [];  % Delete bottom band
            M(:,round(app.DmdPosition(4)):end) = [];    % Delete top band
            kScale = 768/app.DmdPosition(4);              % kScale = H_dmd / H_hama
            translaRight = round(128/kScale - app.DmdPosition(1)); 
            MM = imtranslate(M,[0 translaRight],'FillValues',0,...
            'OutputView','full'); % Translate right (add left band)

% 500 x 500 square case
%             kScale = 500/app.DmdPosition(4);              % kScale = H_dmd / H_hama
%             M(:,round(app.DmdPosition(2)+app.DmdPosition(4)+134/kScale):end) = [];  % Delete bottom band
%             M(:,round(1:app.DmdPosition(2)+134/kScale)) = [];    % Delete top band
%                         translaRight = round(262/kScale - app.DmdPosition(1)); 
%             MM = imtranslate(M,[0 translaRight],'FillValues',0,...
%             'OutputView','full'); % Translate right (add left band)
        
            [d1 d2] = size(MM);
            MM(d1+1:round(1024/kScale),:) = 0;  % Add right band to get 1024x768 ratio
            if ~app.AddToMaskFlag.Value
                app.resetMask();
            end
            app.Mask(imresize(MM,[1024 768])) = 0;
            app.HamamatsuMask(tempMask) = 0;

            
        end
                
        function resetMask(app, hObjects, eventData)
            app.Mask = 255 * uint8(ones(1024,768));
            app.HamamatsuMask = logical(ones(2048));
        end        
      
        function saveMaskedImage(app, hObjects, eventData)
            tempImg = app.ImageCamera;
            tempImg(app.HamamatsuMask) = 0;
            tempName = app.ImageCameraName;
            imwrite(tempImg, [app.Folder tempName(1:end-4) '-masked.tif']);

        end
        
        function uploadMask(app, hObjects, eventData)
            app.DmdDevice.stop();
            pause(0.2);
            app.DmdDevice.load(app.Mask);
            app.DmdDevice.start();             
        end      
               
        function initDmdSequence(app, hObjects, eventData)
            app.CurrentMaskNb = 0;          
        end
        
        function showNextMask(app, hObjects, eventData)
            if ~isempty(app.MaskSequence)
                app.CurrentMaskNb = app.CurrentMaskNb + 1;
                if app.CurrentMaskNb > size(app.MaskSequence,3)
                    app.CurrentMaskNb = 1;
                end
                app.Mask = app.MaskSequence(:,:,app.CurrentMaskNb);
                app.uploadMask();
            end
        end
        
        function resetSequence(app, hObjects, eventData)
            app.MaskSequence = [];
        end
                
        function addMaskToSequence(app, hObjects, eventData)
            if isempty(app.MaskSequence)
                app.MaskSequence(:,:)=app.Mask;
            else
                app.MaskSequence(:,:,end+1) = app.Mask;
            end
        end
           
        
        
    end
end