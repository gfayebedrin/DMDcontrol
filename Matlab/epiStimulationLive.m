classdef epiStimulationLive < handle
% epiStimulation Define regions of stimulation from epi-fluorescence arm
%
% Select in the live preview image a region of interest to be illuminated
% by the DMD setup

    properties
        
        CameraFigure        % Main figure, contains the live preview
        ControlsVideo       % Figure for display controls
        ControlsDMD         % Figure for DMD controls               
        VideoInput          % imaq video input object
        ImageCamera         % imaq preview output's destination image
        PreviewHandle       % imaq preview output handle
        Contrast            % Controls for adjusting the display's contrast
        ExposureTime        % Exposure time for the Hamamatsu camera (ms)
        RectangleTarget     % Rectangle object drawn on live preview
        RectangleLimits     % Position of the rectangle
        SnapshotNumber = 1; % Counter to avoid deleting previous snapshots
        DmdDevice           % DMD Object
        Mask                % Mask to be sent to the DMD
        DmdPosition         % [left bottom width height] of DMD  square zone on Hamamatsu image
        DmdTranslation      % Translation vector to go from Hamamatsu image corner to DMD
        DmdScale            % Scale factor to go from Hamamatsu to DMD
    end
    
    methods
        
        function app = epiStimulationLive
            
            app.cameraFigureMaker(app);
                                                          
            app.uiMaker(app);
            
            app.DmdDevice = DMD.Alp;
            
            app.resetMask();
            app.uploadMask();

        end
        
        function closeApp(app,hObject,eventdata)
            % Closes the app
            delete(app.CameraFigure)
            delete(app.ControlsVideo)
            delete(app.ControlsDMD);
            delete(app.DmdDevice);
            imaqreset;
        end
        
        function cameraFigureMaker(app,hObject,eventdata)
            % Creates the figure containing the camera preview
            app.VideoInput = videoinput('hamamatsu'); 
            app.CameraFigure = figure('Toolbar','none',...
                 'Menubar', 'none',...
                 'NumberTitle','Off',...
                 'Name','Preview',...
                 'OuterPosition', [10 220 700 700],...
                 'CloseRequestFcn',@app.closeApp) ;
                 
            vidRes = app.VideoInput.VideoResolution;
            imWidth = vidRes(1);
            imHeight = vidRes(2);
            nBands = app.VideoInput.NumberOfBands;
            app.ImageCamera = image(0,0, zeros(imHeight, imWidth, nBands));
            
            setappdata(app.ImageCamera,...
                'UpdatePreviewWindowFcn',@app.adjustImage);
        end
        
        function uiMaker(app,hObject,eventdata)
            % Constructs the various windows of the user interface
            
            %------------------------------------------------------------%
            % Controls for camera preview
            %------------------------------------------------------------%
            
            app.ControlsVideo = figure('Toolbar','none',...
                 'Menubar', 'none',...
                 'NumberTitle','Off',...
                 'Name','Controles Video',...
                 'OuterPosition', [10 30 700 180],...
                 'CloseRequestFcn',@app.closeApp) ;
                         
            uicontrol(app.ControlsVideo,'String', 'Start Preview',...
                'Callback', @app.preview,...
                'Position',[5 75 75 30]);
            uicontrol(app.ControlsVideo,'String', 'Stop Preview',...
                'Callback', @app.stoppreview,...
                'Position',[5 40 75 30]);
            uicontrol(app.ControlsVideo,'String', 'Close',...
                'Callback', @app.closeApp,...
                'Position',[5 5 75 30]);
            uicontrol(app.ControlsVideo,'String', 'Snapshot',...
                'Callback', @app.getSnap,...
                'Position',[85 75 75 30]);
            app.Contrast{1} = uicontrol(app.ControlsVideo,...
                'Style', 'slider',...
                'Value', 1,...
                'Min', 1,...
                'Max', 10,...
                'Position',[85 5 500 10]);
            app.Contrast{2} = uicontrol(app.ControlsVideo,...
                'Style', 'slider',...
                'Value', 1,...
                'Min', 0,...
                'Max', 100,...
                'Position',[85 20 500 10]);
            app.ExposureTime = uicontrol(app.ControlsVideo,...
                'Style', 'edit',...
                'Value', 10,...
                'Callback', @app.setExposureTime,...
                'Position', [85 35 30 20]);
            
            %------------------------------------------------------------%
            % Controls for DMD mask
            %------------------------------------------------------------%
            
            app.ControlsDMD = figure('Toolbar','none',...
                 'Menubar', 'none',...
                 'NumberTitle','Off',...
                 'Name','Controles DMD',...
                 'OuterPosition', [750 30 300 180],...
                 'CloseRequestFcn',@app.closeApp) ;
            
            uicontrol(app.ControlsDMD,'String', 'Draw',...
                'Callback', @app.myDraw,...
                'Position',[5 110 75 30]);
            app.RectangleLimits{1} = uicontrol(app.ControlsDMD,...
                'style','text','String','x', ...
                'Position',[15 75 20 15]);
            app.RectangleLimits{2} = uicontrol(app.ControlsDMD,...
                'style','text','String','y', ...
                'Position',[15 40 20 15]);
            app.RectangleLimits{3} = uicontrol(app.ControlsDMD,...
                'style','text','String','W', ...
                'Position',[45 75 20 15]);
            app.RectangleLimits{4} = uicontrol(app.ControlsDMD,...
                'style','text','String','H', ...
                'Position',[45 40 20 15]);
            uicontrol(app.ControlsDMD,'String', 'Add to mask',...
                'Callback', @app.addToMask,...
                'Position',[110 110 75 30]);
            uicontrol(app.ControlsDMD,'String', 'Reset Mask',...
                'Callback', @app.resetMask,...
                'Position',[110 75 75 30]);
            uicontrol(app.ControlsDMD,'String', 'Preview Mask',...
                'Callback', @app.previewMask,...
                'Position',[110 40 75 30]);
            uicontrol(app.ControlsDMD,'String', 'Upload Mask',...
                'Callback', @app.uploadMask,...
                'Position',[110 5 75 30]);
            uicontrol(app.ControlsDMD,'String', 'Calibrate DMD',...
                'Callback', @app.calibrateDMD,...
                'Position',[200 5 75 30]);
        end
        
        function adjustImage(app, hObject, eventdata ,himage)
            himage.CData = (eventdata.Data - app.Contrast{2}.Value) * app.Contrast{1}.Value;
        end  
        
        function preview(app, hObject, eventdata)
           app.PreviewHandle = preview(app.VideoInput, app.ImageCamera);
        end
        
        function stoppreview(app, hObject, eventdata)
            stoppreview(app.VideoInput);
        end
        
        function setExposureTime(app, hObject, eventdata)
            src = getselectedsource(app.VideoInput);
            src.ExposureTime = str2num(app.ExposureTime.String)/1000;            
        end
        
        function calibrateDMD(app, hObject, eventdata)
            app.resetMask();
            app.Mask(128:end-128,:) = 0; % Full Height Square (768x768)
            app.uploadMask();
            app.DmdPosition = getrect(ancestor(app.ImageCamera,'axes'));
            app.resetMask();
            app.uploadMask();
        end
        
        function myDraw(app, hObject, eventdata)
              h = imfreehand(ancestor(app.ImageCamera,'axes'));
              M = h.createMask();
              M = flip(flip(M',1),2);
              M(:,end-round(app.DmdPosition(2)):end) = [];  % Delete bottom band
              M(:,1:end-round(app.DmdPosition(4))) = [];    % Delete top band
              kScale = 768/app.DmdPosition(4);              % kScale = H_dmd / H_hama
              translaRight = round(128/kScale -(2048 - app.DmdPosition(1) - app.DmdPosition(3))); 
              MM = imtranslate(M,[0 translaRight],'FillValues',0,...
                  'OutputView','full'); % Translate right (add left band)
              [d1 d2] = size(MM);
              MM(d1+1:round(1024/kScale),:) = 0;  % Add right band to get 1024x768 ratio
              %size(MM)
              app.resetMask();
              %app.Mask(imresize(flip(flip(MM',1),2),[1024 768])) = 0;
              app.Mask(imresize(MM,[1024 768])) = 0;
              app.uploadMask();
        end
        
        function getSnap(app, hObject, eventdata)
            imwrite(getsnapshot(app.VideoInput),['snapshot' num2str(app.SnapshotNumber) '.jpg']);
            app.SnapshotNumber = app.SnapshotNumber + 1;
        end
        
        function addToMask(app, hObject, eventdata)
            % Add light (0) to the zone of the current rectangle
            l_rect = app.RectangleTarget.Position(1);
            b_rect = app.RectangleTarget.Position(2);
            w_rect = app.RectangleTarget.Position(3);
            h_rect = app.RectangleTarget.Position(4);
            
            l_dmd = app.DmdPosition(1);
            b_dmd = app.DmdPosition(2);
            w_dmd = app.DmdPosition(3);
            h_dmd = app.DmdPosition(4);
            
            app.Mask(l_rect - l_dmd:floor(w_rect*1024/w_dmd) , b_rect - b_dmd:floor(h_rect*768/h_dmd)) = 0;
        end
        
        function resetMask(app, hObject, eventdata)
            app.Mask = 255 * uint8(ones(1024,768));
        end        
      
        function previewMask(app, hObject, eventdata)
            imtemp = getsnapshot(app.VideoInput);
            
        end
        
        function uploadMask(app, hObject, eventdata)
            app.DmdDevice.stop();
            pause(0.2);
            app.DmdDevice.load(app.Mask);
            app.DmdDevice.start();             
        end        
           
        
        
    end
end