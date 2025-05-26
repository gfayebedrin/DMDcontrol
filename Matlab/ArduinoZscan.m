classdef ArduinoZscan < handle
       
    properties
        
        GUI
        ComPortArduino  = 'COM6';
        ComPortStage    = 'COM4';
        HdlArduino
        HdlStage
        SavingFolder
        StepCtrl
        Step            = 10;           % in 0.1 µm unit
        ZStart
        ZEnd
        ExposureTimeDelay = 0.1;
        StageMovementDelay = 0.2;
        
    end
    
    methods
        
        function app = ArduinoZscan
            
            app.guiMaker();
            
            app.initCom();            
            
        end
        
        function guiMaker(app,hObject,eventdata)
            
            app.GUI = figure('MenuBar','none',...           
                'NumberTitle','off',...
                'Name','Arduino Z Stack',...
                'Position',[200 300 300 80],...
                'CloseRequestFcn',@app.closeApp);
            
            uicontrol(app.GUI,...
                'Position',[10 55 90 20],...
                'String','Select Folder',...
                'Callback', @app.selectFolder);
                   
            uicontrol(app.GUI,...
                'Position',[110 30 90 20],...
                'String','Show Z pos.',...
                'Callback', @app.showZpos);
            
            uicontrol(app.GUI,...
                'Position',[110 5 90 20],...
                'String','End here',...
                'Callback', @app.setEnd);
            
            uicontrol(app.GUI,...
                'Style','text',...
                'Position',[110 55 60 20],...
                'String','Step (µm)');
            
            app.StepCtrl = uicontrol(app.GUI,...
                'Style','edit',...
                'String','1',...
                'Position',[170 55 20 20],...
                'Callback', @app.setStep);
            
            uicontrol(app.GUI,...
                'Position',[205 30 90 20],...
                'String','Launch Z Stack',...
                'Callback', @app.launchStack);
            
            uicontrol(app.GUI,...
                'Position',[205 5 90 20],...
                'String','Save Current Z',...
                'Callback', @app.saveZPos);
        end
        
        function closeApp(app,hObject,eventdata)
            fclose(app.HdlArduino);
            fclose(app.HdlStage);
            
            delete(app.GUI);
        end
        
        function initCom(app,hObject,eventdata)
            
            app.HdlArduino = serial(app.ComPortArduino,'BaudRate',115200);
            fopen(app.HdlArduino);
            
            app.HdlStage = serial(app.ComPortStage,...
                'BaudRate', 9600,...
                'Terminator','CR');
            fopen(app.HdlStage);
            
            
        end
        
        function selectFolder(app,hObject,eventdata)
            app.SavingFolder = uigetdir;
        end
                        
        function setStart(app,hObject,eventdata)
            app.ZStart = app.getZ();
            fprintf(['Start Z position is: ' num2str(app.ZStart/10) '\n']);
        end
        
        function setEnd(app,hObject,eventdata)
            app.ZEnd = app.getZ();
            fprintf(['End Z position is: ' num2str(app.ZEnd/10) '\n']);
        end
        
        function setStep(app,hObject,eventdata)
            app.Step = 10 * str2double(get(app.StepCtrl,'String'));
        end
        
        function launchStack(app,hObject,eventdata)
            app.setStart();
            if app.ZStart > app.ZEnd
                app.Step = -app.Step;
            end
            Nsteps = round((app.ZEnd - app.ZStart)/app.Step);
            
            f = waitbar(0,' ','Name','Performing Z stack...',...
                'CreateCancelBtn','setappdata(gcbf,''canceling'',1)');
            setappdata(f,'canceling',0);
            
            fprintf(['Performing Z stack of ' num2str(Nsteps) ' positions\n']);
            for i=1:Nsteps
                if getappdata(f,'canceling')
                    break
                end
                app.trigCamera();
                pause(app.ExposureTimeDelay);
                fprintf(app.HdlStage,['relz ' num2str(app.Step)]);
                pause(app.StageMovementDelay);
                fscanf(app.HdlStage);
                waitbar(i/Nsteps,f);
            end
            
            fprintf(['Z stack complete\n']);
            delete(f);
        end
        
        function saveZPos(app,hObject,eventdata)
            answer = questdlg('Is the correct folder selected?',...
                'Overwrite prevention check','Yes', 'No','Yes');
            
            if strcmp(answer,'Yes')
                fileHandle = fopen([app.SavingFolder filesep 'Z_of_recording.txt'],'w');
                fprintf(fileHandle, num2str(app.getZ()));
                fclose(fileHandle);
            end
        end
        
        function ret = getZ(app,hObject,eventdata)
                fprintf(app.HdlStage,'pz');
                ret = str2double(fscanf(app.HdlStage));
        end
        
        function trigCamera(app,hObject,eventdata)
                fprintf(app.HdlArduino,'t');
        end
        
        function showZpos(app,hObject,eventdata)
                fprintf(['Current Z position is: ' num2str(app.getZ()/10) '\n']);
        end
    end
end


