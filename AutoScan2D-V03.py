import wx
import wx.lib.buttons as buttons
import serial
import time
import threading
import pickle
import wx.lib.plot
import os, sys
import numpy as np


#Combine translation stage with data-acquisition
#translation stage is controlled by Arduino running Grbl
#data acquisition is controlled by Parallax-Propeller (DataSpider module)
#starting 2D based on AutoScanSimple-V07A   25 May 2018  -  Frederic Durville
#---V00-25may18
# for simplicity, we will keep the same StepSize and TotalTravel for both X (hor) and Y (vert) axis
# 31may18 - FD added buttons on GUI to manual move stage X and Y
#V02 - 29jun18
#V02B - 13jul18 - FD - added chksum check in readData and discard "0" data
#V03 - started 13jul18
#implementing a timer for dataAcquisition to allow interupting data acquisition
#cleaned up a few things - V03 working 16jul18


title = "CNC 2D X-Y Scan - All values in mm and seconds"
xSize = 800         #H-size of window frame
ySize = 600         #V-size of window frame
btnSize = 40        #size of START button
panelWidth = 180    #width of left panel

#setting default values for grbl / CNC control
grblPort = 'COM13'  # COM13 for Xtreme - COM7 for lab
grblbdr = 115200
travelSpeed = 400
step = 0.1
travel = 1
analogIn = '0'
duration = 0.1

#setting default values for DataSpider / data acquisition control
propPort = 'COM9'   # COM9 for Xtreme - COM4 for lab
propbdr = 115200

EOP = "|"
ESC = "`"
CLOCKPERSEC = 80000000
samplingRate = 200 # sampling rate in samples per second
rateVal = CLOCKPERSEC / samplingRate
msgID = 1
tout = 0.5
# keyTable = {0:"talk",1:"over",2:"bad",3:"version",4:"start",5:"stop",
#6:"set",7:"dir",8:"query",9:"info",10:"dig",11:"wav",12:"point",
#13:"sync",14:"avg",15:"timer",16:"event",17:"resetevent",18:"trigger")} 
keyTable = ["talk","over","bad","version","start","stop","set","dir",\
            "query","info","dig","wav","point","sync",\
            "avg", "timer", "event", "resetevents", "trigger"]


nptMax = 1000
data = []
img = np.empty((nptMax,nptMax))

#storing values in a single array
dataInput = [grblPort, step, travel, analogIn ,duration, propPort]

colorTable = [ "blue", "red", "green", "yellow", "purple", "black" ]
xlabel = "mm"
ylabel = "Value"
maxVal = 4095
minVal = 0
stepDelay = 0.1
nstp = 0
nbStep = 10
gcodeStep = ''
s = serial.Serial()
prop = serial.Serial()


class MyFrame(wx.Frame):
    def __init__(self, parent, title, xSize, ySize, panelWidth):
        wx.Frame.__init__(self, parent, panelWidth, title=title, size=(xSize, ySize))

        loc = wx.IconLocation('OFSI.ico', 0)
        self.SetIcon(wx.IconFromLocation(loc))

        #timer used for data-acquisition
        self.stepTimer = wx.Timer(self)

        #setting up variable with default values
        self.userInput = ['grblPort','step','travel','AI-','duration','propPort']
        self.grblPort = dataInput[0]
        self.step = dataInput[1]
        self.travel = dataInput[2]
        self.analogIn = dataInput[3]
        self.duration = dataInput[4]
        self.propPort = dataInput[5]

        print "default values: ", self.grblPort, self.step, self.travel,\
                        self.analogIn, self.duration, self.propPort
        
        #setting up a vertically-split window
        self.splitter = wx.SplitterWindow(self, -1, style=wx.SP_LIVE_UPDATE)
        font = wx.Font(12,wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False)

        self.grblPanel = wx.Panel(self.splitter, -1)
        self.graphPanel = wx.Panel(self.splitter, -1)
        self.graphPanel.SetBackgroundColour(wx.WHITE)

        self.splitter.SplitVertically(self.grblPanel, self.graphPanel,panelWidth)

        self.grblLabel = wx.StaticText(self.grblPanel, -1, 'XY Stage Controls')
        self.grblLabel.SetFont(font)
        self.controlLabel = wx.StaticText(self.grblPanel, -1, 'Data Controls')
        self.controlLabel.SetFont(font)

        # add plot
        self.plotSizer = wx.BoxSizer(wx.VERTICAL)
        self.plot = wx.lib.plot.PlotCanvas(self.graphPanel, size=wx.Size(500,500), style=wx.EXPAND)
        self.plot.SetShowScrollbars(False)

        #defining event handlers
        def getComPort(event):
            self.grblPort = self.comPort.GetValue()
            print "selected port: ", self.grblPort
            dataInput[0] = self.grblPort
            return self.grblPort

        def getStep(event):
            self.step = float(self.stepSize.GetValue())
            print "step: ", self.step
            dataInput[1] = self.step
            return self.step

        def getTravel(event):
            self.travel = float(self.totalTravel.GetValue())
            print "travel: ", self.travel
            dataInput[2] = self.travel
            return self.travel
    
        def getPropPort(event):
            self.propPort = self.propComPort.GetValue()
            print "selected prop port: ", self.propPort
            dataInput[5] = self.propPort
            return self.propPort

        def getChanIn(event):
            self.analogIn = self.chanIn.GetValue()
            print "selected AI-",self.analogIn
            dataInput[3] = self.analogIn
            updateGraph(self.plot)
            return self.analogIn

        def getDuration(event):
            self.duration = float(self.durAcq.GetValue())
            print "duration: ", self.duration
            dataInput[4] = self.duration
            return self.duration

        def getBillboard(event):
            #time.sleep(1)
            billboard = BillboardDisplay(self, dataInput)
            billboard.Show()

        def moveLeft(event):
            global s
            grblPort = dataInput[0]
            step = dataInput[1]
            try:
                if s is None:
                    startArduino(grblPort)
                else:
                    if not s.isOpen():
                        s.open()
            except:
                startArduino(grblPort)
            gcode = 'G01 X-'  + str(step)
            sendCode(gcode)

        def moveRight(event):
            global s
            grblPort = dataInput[0]
            step = dataInput[1]
            try:
                if s is None:
                    startArduino(grblPort)
                else:
                    if not s.isOpen():
                        s.open()
            except:
                startArduino(grblPort)
            gcode = 'G01 X'  + str(step)
            sendCode(gcode)

        def moveDown(event):
            global s
            grblPort = dataInput[0]
            step = dataInput[1]
            try:
                if s is None:
                    startArduino(grblPort)
                else:
                    if not s.isOpen():
                        s.open()
            except:
                startArduino(grblPort)
            gcode = 'G01 Y-'  + str(step)
            sendCode(gcode)

        def moveUp(event):
            global s
            grblPort = dataInput[0]
            step = dataInput[1]
            try:
                if s is None:
                    startArduino(grblPort)
                else:
                    if not s.isOpen():
                        s.open()
            except:
                startArduino(grblPort)
            gcode = 'G01 Y'  + str(step)
            sendCode(gcode)

        def getStart(event):
            self.value = self.pulseBtn.GetValue()
            if self.value:
                if len(data) != 0:
                    del data[0:len(data)]
                self.btnLabel.SetLabel('STOP')
                imgData = startScan(self,self.plot)
                #print "RETURNING - COMPLETE"
                #print imgData
            else:
                self.btnLabel.SetLabel('START')

        def getSave(event):
            print "saving data..."
            header = "Data from AutoScan2D V03"
            saveData(self,header)
            

        # grbl-COM-Port combobox Control
        self.portList = ['COM3','COM4','COM5','COM6','COM7','COM8', 'COM9', 'COM10', 'COM11', 'COM12','COM13']
        self.portLabel = wx.StaticText(self.grblPanel, label="Grbl Port")
        self.comPort = wx.ComboBox(self.grblPanel, choices=self.portList, value=self.grblPort, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getComPort, self.comPort)
        s1 = wx.BoxSizer(wx.HORIZONTAL)
        s1.Add(self.portLabel, 0, wx.ALL,5)
        s1.Add(self.comPort, 0, wx.ALL,5)

        #step size entry box
        self.stepLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Step Size')
        self.stepSize = wx.TextCtrl(self.grblPanel, wx.ID_ANY, str(self.step), style=wx.TE_PROCESS_ENTER)
        self.stepSize.Bind(wx.EVT_TEXT_ENTER, getStep)
        s2 = wx.BoxSizer(wx.HORIZONTAL)
        s2.Add(self.stepLabel, 0, wx.ALL,5)
        s2.Add(self.stepSize, 0, wx.ALL,5)

        #total travel entry box
        self.travelLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Total Travel')
        self.totalTravel = wx.TextCtrl(self.grblPanel, wx.ID_ANY,str(self.travel),style=wx.TE_PROCESS_ENTER)
        self.totalTravel.Bind(wx.EVT_TEXT_ENTER, getTravel)
        s3 = wx.BoxSizer(wx.HORIZONTAL)
        s3.Add(self.travelLabel, 0, wx.ALL,5)
        s3.Add(self.totalTravel, 0, wx.ALL,5)

        # CH-IN combobox Control
        self.chanList = ['0', '1', '2', '3']
        self.chanLabel = wx.StaticText(self.grblPanel, label="Analog Input")
        self.chanIn = wx.ComboBox(self.grblPanel, choices=self.chanList, value=self.analogIn, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getChanIn, self.chanIn)
        s21 = wx.BoxSizer(wx.HORIZONTAL)
        s21.Add(self.chanLabel, 0, wx.ALL,5)
        s21.Add(self.chanIn, 0, wx.ALL,5)

        #acquisition duration entry box
        self.durationLabel = wx.StaticText(self.grblPanel, wx.ID_ANY, 'Duration')
        self.durAcq = wx.TextCtrl(self.grblPanel, wx.ID_ANY,str(self.duration),style=wx.TE_PROCESS_ENTER)
        self.durAcq.Bind(wx.EVT_TEXT_ENTER, getDuration)
        s22 = wx.BoxSizer(wx.HORIZONTAL)
        s22.Add(self.durationLabel, 0, wx.ALL,5)
        s22.Add(self.durAcq, 0, wx.ALL,5)

        # Prop COM-Port combobox Control
        self.propPortLabel = wx.StaticText(self.grblPanel, label="Prop Port")
        self.propComPort = wx.ComboBox(self.grblPanel, choices=self.portList, value=self.propPort, style=wx.CB_READONLY)
        self.Bind(wx.EVT_COMBOBOX, getPropPort, self.propComPort)
        s23 = wx.BoxSizer(wx.HORIZONTAL)
        s23.Add(self.propPortLabel, 0, wx.ALL,5)
        s23.Add(self.propComPort, 0, wx.ALL,5)

        #setting up "billboard" button
        self.billboardBox = wx.StaticBox(self.grblPanel, -1, 'Display Live Data')
        self.billboardBox.SetFont(font)
        s24 = wx.StaticBoxSizer(self.billboardBox, wx.VERTICAL)
        self.billboardBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " - BILLBOARD - ", size = (140,-1))
        self.billboardBtn.Bind(wx.EVT_BUTTON, getBillboard)
        s24.Add(self.billboardBtn, 0, wx.EXPAND, 0)
        
        #setting up manual movement of stage
        self.moveStageBox = wx.StaticBox(self.grblPanel, -1, 'Move Stage')
        self.moveStageBox.SetFont(font)
        s25 = wx.StaticBoxSizer(self.moveStageBox, wx.VERTICAL)
        self.stageNote = wx.StaticText(self.grblPanel, label = '(increments of Step Size)')
        stageNoteSizer = wx.BoxSizer(wx.VERTICAL)
        stageNoteSizer.Add(self.stageNote, 0, wx.ALIGN_CENTER)
        stageNoteSizer.AddSpacer(10)
        s25.Add(stageNoteSizer, 0, wx.ALIGN_LEFT, 0)

        #Added labels X and Y, and buttons Dwon and Up - FD 31may18

        self.horizontalNote = wx.StaticText(self.grblPanel, label = "Horizontal X")
        horizontalNoteSizer = wx.BoxSizer(wx.VERTICAL)
        horizontalNoteSizer.Add(self.horizontalNote, 0, wx.ALIGN_CENTER)
        s25.Add(horizontalNoteSizer, 0, wx.ALIGN_CENTER, 0)

        
        self.moveLeftBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " <<< ", size = (70,-1))
        self.moveRightBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " >>> ", size = (70,-1))
        self.moveLeftBtn.Bind(wx.EVT_BUTTON, moveLeft)
        self.moveRightBtn.Bind(wx.EVT_BUTTON, moveRight)
        moveBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
        moveBtnSizer.Add(self.moveLeftBtn,0,wx.CENTER)
        moveBtnSizer.Add(self.moveRightBtn, 0, wx.CENTER)
        s25.Add(moveBtnSizer, 0, wx.EXPAND, 0)

        self.verticalNote = wx.StaticText(self.grblPanel, label = "Vertical Y")
        verticalNoteSizer = wx.BoxSizer(wx.VERTICAL)
        verticalNoteSizer.Add(self.verticalNote, 0, wx.ALIGN_CENTER)
        s25.Add(verticalNoteSizer, 0, wx.ALIGN_CENTER, 0)

        
        self.moveDownBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "\/ \/", size = (70,-1))
        self.moveUpBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = " /\ /\ ", size = (70,-1))
        self.moveDownBtn.Bind(wx.EVT_BUTTON, moveDown)
        self.moveUpBtn.Bind(wx.EVT_BUTTON, moveUp)
        moveYBtnSizer = wx.BoxSizer(wx.HORIZONTAL)
        moveYBtnSizer.Add(self.moveDownBtn,0,wx.CENTER)
        moveYBtnSizer.Add(self.moveUpBtn, 0, wx.CENTER)
        s25.Add(moveYBtnSizer, 0, wx.EXPAND, 0)


        
        
        #setting up START toggle button with custom bitmap
        self.pulseOn = scale_bitmap(wx.Bitmap("record-button-on.png"), btnSize, btnSize)
        self.pulseOff = scale_bitmap(wx.Bitmap("record-button-off.png"),btnSize, btnSize)

        self.btnLabel = wx.StaticText(self.grblPanel, label="START")
        self.pulseBtn = buttons.GenBitmapToggleButton(self.grblPanel, id=wx.ID_ANY, bitmap=self.pulseOff)
        self.pulseBtn.SetBitmapSelected(self.pulseOn)
        self.pulseBtn.Bind(wx.EVT_BUTTON, getStart)

        s31 = wx.BoxSizer(wx.VERTICAL)
        s31.Add(self.btnLabel, 0, wx.ALIGN_CENTER_HORIZONTAL,0)
        s31.Add(self.pulseBtn, 0, wx.ALIGN_CENTER_HORIZONTAL,0)

        #setting up "SAVE" button
        self.saveBtn = wx.Button(self.grblPanel, id=wx.ID_ANY, label = "SAVE")
        self.saveBtn.Bind(wx.EVT_BUTTON, getSave)
        s31.Add(self.saveBtn, 0, wx.ALIGN_CENTER_HORIZONTAL, 0)
        

       #setting up the sizers for grblPanel
        grblPnlLblSizr = wx.BoxSizer(wx.HORIZONTAL)
        grblPnlLblSizr.Add(self.grblLabel, wx.ALL, 10)

        controlLblSizr = wx.BoxSizer(wx.HORIZONTAL)
        controlLblSizr.Add(self.controlLabel, wx.ALL, 10)
        
        grblPnlSizr = wx.BoxSizer(wx.VERTICAL)
        grblPnlSizr.Add(grblPnlLblSizr, 0, wx.CENTER)
        grblPnlSizr.Add(wx.StaticLine(self.grblPanel,), 0, wx.ALL|wx.EXPAND, 5)
        grblPnlSizr.Add(s1, 0, wx.CENTER)
        grblPnlSizr.Add(s2, 0, wx.CENTER)
        grblPnlSizr.Add(s3, 0, wx.CENTER)
        grblPnlSizr.Add(s25, 0, wx.CENTER)
        grblPnlSizr.AddSpacer(8)
        grblPnlSizr.Add(controlLblSizr, 0, wx.CENTER)
        grblPnlSizr.Add(wx.StaticLine(self.grblPanel,), 0, wx.ALL|wx.EXPAND, 5)
        grblPnlSizr.Add(s21, 0, wx.CENTER)
        grblPnlSizr.Add(s22, 0, wx.CENTER)
        grblPnlSizr.Add(s23, 0, wx.CENTER)
        grblPnlSizr.AddSpacer(8)
        grblPnlSizr.Add(s24, 0, wx.CENTER)
        grblPnlSizr.AddSpacer(15)
        grblPnlSizr.Add(s31, 0, wx.CENTER)

        self.grblPanel.SetSizer(grblPnlSizr)

        #updating data graphing
        updateGraph(self.plot)

        #setting up sizers for graphPanel
        self.plotSizer.Add(self.plot,1,wx.EXPAND,0)
        
        graphPnlSizr = wx.BoxSizer(wx.VERTICAL)
        graphPnlSizr.Add(self.plotSizer, 1, wx.EXPAND, 0)

        self.graphPanel.SetSizer(graphPnlSizr)
        self.Layout()

        self.Bind( wx.EVT_CLOSE, self.OnClose )

    def getData(self,event):
        global minVal, maxVal, travelX, travelY, gcodeTravelX, gcodeTravelY, travelSpeed
        global data, img, imgData, totalTravel, travelStep, duration, xstp, ystp, npts
        
        if self.pulseBtn.GetValue():
            if xstp < npts:
                datVal = readData(duration)
                #print "xstp: ",xstp,"ystp: ",ystp
                print "travelY: ", travelY, " travelX: ", travelX, " Data: ", datVal
                if datVal < minVal:
                    minVal = datVal
                if datVal > maxVal:
                    maxVal = datVal + 1
                dataPoint = (travelX,datVal)
                data.append(dataPoint)
                updateGraph(self.plot)
                s.write(str(gcodeTravelX))
                travelX += travelStep
                xstp += 1
            else:
                #print "completed X-scan"
                #goback on X
                travelBackX = 0 - travelX - 1
                s.write(str('G01 F600 X' + str(travelBackX) + '\r \n'))
                s.write(str('G01 F' + str(travelSpeed) + ' X1 \r \n'))
                time.sleep((travelBackX * 1.2)/travelSpeed + 1)

                nData = len(data)
                
                #print "ystp: ", ystp
                #print "nData: ", nData, "xstp: ", xstp, "ystp: ", ystp 

                
                for n in range(nData):
                    #print "ystp: ",ystp,"n:", n, "data:", data[n][1]
                    imgData[ystp,n] = data[n][1]

                #data = []
                del data[:]
                travelX = 0
                xstp = 0
                maxVal = 1
                #print "ystp: ", ystp, "travelY: ", travelY, "totalTravel: ", totalTravel
                     
                if ystp < npts - 1:
                    print "Next Y-step......................"
                    s.write(str(gcodeTravelY))
                    travelY += travelStep
                    ystp += 1
                else:
                    print "completed Y-scan  ... end of data acquisition"
                    travelBackY = 0 - travelY - 1
                    s.write(str('G01 F600 Y' + str(travelBackY) + '\r \n'))
                    s.write(str('G01 F' + str(travelSpeed) + ' Y1 \r \n'))
                    travelY = 0
                    ystp = 0
                    self.stepTimer.Stop()
                    self.pulseBtn.SetValue(False)
                    self.btnLabel.SetLabel('START')
        else:
            print "data acquisition interrupted!"
            print "Returning stages to starting point"
            self.stepTimer.Stop()
            self.pulseBtn.SetValue(False)
            self.btnLabel.SetLabel('START')
            travelBackX = 0 - travelX - 1
            travelBackY = 0 - travelY - 1
            s.write(str('G01 F600 X' + str(travelBackX) + 'Y' + str(travelBackY) + '\r \n'))
            s.write(str('G01 F' + str(travelSpeed) + ' X1 Y1 \r \n'))
            nData = len(data)
            for n in range(nData):
                #print "ystp: ",ystp,"n:", n, "data:", data[n][1]
                imgData[ystp,n] = data[n][1]
            
                
        


    def OnClose(self,event):
        try:
            s.close()
            prop.close()
        except:
            print "couldnot close s or prop"
        self.Destroy()

        


#####second frame to display data value only

class BillboardDisplay(wx.Frame):
    def __init__(self, window_parent, dataInput ):
        self.chan = int(dataInput[3])
        self.duration = 0.1
        self.propPort = dataInput[5]

        global iloop
        global inc
        iloop = 12
        inc = True
        self.timerPeriod = 200

        wx.Frame.__init__(self, window_parent, wx.ID_ANY, "BillBoard - AI" + str(self.chan))
        ico = wx.Icon('OFSI.ico', wx.BITMAP_TYPE_ICO )
        self.SetIcon( ico )

        self.timer = wx.Timer(self)
    
        mainSizer = wx.BoxSizer( wx.VERTICAL )
        panelSizer = wx.BoxSizer( wx.HORIZONTAL )
        self.font = wx.Font(200, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
    
        panel = wx.Panel(self)
        initVal = "0000"
        self.txtValue = wx.StaticText(self, label=initVal)
        self.txtValue.SetFont(self.font)
        self.gaugeMeter = wx.Gauge( self, wx.ID_ANY, 4096, wx.DefaultPosition, \
                        wx.Size( 75,-1 ), wx.GA_VERTICAL|wx.GA_SMOOTH )
        panelSizer.Add(self.txtValue, 0, wx.ALL, 20)
        panelSizer.Add((0,0),1)
        panelSizer.Add(self.gaugeMeter, 0, wx.ALL|wx.EXPAND, 5)
        panel.SetSizer(panelSizer)
        mainSizer.Add(panel, 1, wx.ALL|wx.EXPAND)
        self.SetSizer(mainSizer)
        self.Fit()

        self.startDataRead()
        self.Bind(wx.EVT_TIMER, self.updateValue, self.timer)

        #changed from EVT_MOUSE_EVENTS to EVT_MOUSEWHEEL - works fine - FD 04jun18
        #first wheel clik starts, second one stops
        self.Bind( wx.EVT_MOUSEWHEEL, self.startTimer )
        self.Bind( wx.EVT_CLOSE, self.OnClose )

    def startDataRead(self):
        #global dataInput
        propPort = dataInput[5]
        chIdx = int(dataInput[3])
        startADC(propPort,propbdr,chIdx,rateVal)


    def startTimer(self,event):
        print "starting timer....."
        chIdx = int(dataInput[3])
        if self.timer.IsRunning():
            self.timer.Stop()
           #print "stopped ADC Chan-",chIdx
        else:
            self.timer.Start(self.timerPeriod)

    #read ADC and update value on billboard and gauge
    def updateValue(self,event):
        duration = 0.05
        value = readData(duration)
        self.label = "{0:04}".format( value )
        self.txtValue.SetLabel(self.label)
        self.gaugeMeter.SetValue(value)

    def OnClose(self, event):
        chIdx = int(dataInput[3])
        if self.timer.IsRunning():
            self.timer.Stop()
            #ttt = send(nextMsgID(msgID), prop,'stop',2**chIdx)  #stop ADC
            print "stoppped timer "
        try:
            stopADC(chIdx)
            print "stoppped ADC Chan "
        except:
            print "Can't close prop"
        self.Destroy()


###-----  function to define graphing of data --------------
def updateGraph(plot):  #plot is the panel on which the PlotCanvas is defined
    global maxVal, minVal, data
    travel = dataInput[2]
    nPoints = len(data)
    #print "nPoints: ", nPoints
    #print "maxval: ", maxVal
    max_X = travel
    displayData = data
    lastX = max_X/2.0
    
    if maxVal > 0 :
        maxY = maxVal * 1.1
    else:
        maxY = 4095

    if maxY is not None:
        lastY = maxY/2.0
    else:
        lastY = 0
    lastpoint = (lastX, lastY)
    showPoints = False
    lines = []
        
    # draw points as a line
    line = wx.lib.plot.PolyLine(data, colour='red', width=1)
    plotTitle = "Plot AI-" + dataInput[3]
    marker = wx.lib.plot.PolyMarker(data, marker='triangle') #not used for the moment
    pg = wx.lib.plot.PlotGraphics([line], plotTitle, xlabel, ylabel)

    xRange = (0, travel)
    yRange = (minVal, maxY )

    plot.Draw(pg, xRange, yRange)

###-----  End of graphing data function --------------


#Starting scan: moving stage and acuiring data
def startScan(self,panelPlot):
    global s, data, minVal, maxVal, img, imgData, npts, dataInput, xstp, ystp, npts
    global travelX, travelY, gcodeTravelX, gcodeTravelY, travelStep, duration, totalTravel

    #initializing all variables
    propPort = dataInput[5]
    chIdx = int(dataInput[3])
    grblPort = dataInput[0]
    travelStep = dataInput[1]
    totalTravel = float(dataInput[2])
    duration = dataInput[4]
    npts = int(totalTravel / travelStep) + 1
    print "Nb Points: ",(npts * npts)
    imgData = img[:npts,:npts]
    imgData.fill(0)
    travelX = 0
    travelY = 0
    gcodeTravelX = 'G01 X'  + str(travelStep) + '\r \n'
    gcodeTravelY = 'G01 Y'  + str(travelStep) + '\r \n'
    ystp = 0
    xstp = 0
    minVal = 0
    maxVal = 1

    #check and validate all input data
    try:
        ii = 0
        for dat in ['grblPort','step','travel','AI-','duration','propPort']:
            print dat, dataInput[ii]
            if dataInput[ii] == 0 and ii!=3:
                raise ValueError
            ii += 1
        if not dataInput[2] > dataInput[1]:
            print "error: travel NOT> step"
            raise ValueError
    except ValueError:
        print "invalid datainput"

    #making sure that the Arduino-grbl is initialized
    try:
        if s is None:
            startArduino(grblPort)
        else:
            if not s.isOpen():
                s.open()
    except:
        startArduino(grblPort)

    #starting the ADC channel on DataSpider / propcom
    startADC(propPort,propbdr,chIdx,rateVal)
    
    time.sleep(0.2)

    #print "starting dataAcquisition...."
    #use a timer to initiate each data reading
    self.Bind(wx.EVT_TIMER, self.getData, self.stepTimer)
    stepDelay = (0.1 + (dataInput[1]*60/travelSpeed))*1000
    stepPeriod = int(duration*1000 + stepDelay)
    self.stepTimer.Start(stepPeriod,wx.TIMER_CONTINUOUS)
    


# Loop to just read and display data from propeller
def readData(duration):
    global prop
    chIdx = int(dataInput[3])
    #print "duration: ", duration
    datVal = 0
    nn = 0
    nc = 0
    dd = 0
    de = 0
    
    while dd == 0:
        val = []   # store values of individual data point
        nb = 0
        t = time.time() + duration
        prop.flushInput()
        while t - time.time() > 0:
            time.sleep(0.0002)
        try:
            nb = prop.inWaiting()
        except:
            print "error - no bytes received"
            dd = 0


        if nb > 12:
            msg = prop.read(prop.inWaiting())
            #print "Nb Bytes: ", nb
            nc = 0
            chk = 0
            for c in msg:
                #print "c: ",ord(c), " - nc: ", nc
                if ord(c) == 124:
                    #print "found EOP  ", "nc",nc,"ID",ord(msg[nc - 10])
                    nn += 1
                    if nc < (len(msg) - 1) and nc > 9 and ord(msg[nc - 10]) == 12: #-out FD 12jul18 11:57am
                        #verifying chksum
                        chk = ord(msg[nc+1])    #chksum value of message sent
                        chksum = 0
                        for ii in range(0,10):  #computing chksum of message received
                            chksum = ((chksum<<1) | (chksum>>7)) & 255  # left-rotate
                            chksum = (chksum + ord(msg[nc - (10 - ii)])) & 255  # 8-bit addition
                        if chksum == chk:       #chksums match valid data
                            pVal = ord(msg[nc - 5]) + (ord(msg[nc - 6]) & 15) * 256
                            val.append(pVal)    #store all good values in list val
                        else:
                            #not sure what to do if chksums do not match. At this point, just skip data packet
                            pass
                    else:
                        pass    #the EOP does not match a data packet FD 12jul18
                    #print "sent chk: ", chk, "received: ", chksum
                   
                nc += 1
                #print "nb pts: ",len(val)
            
        if val is not None and len(val) != 0:
            datVal = sum(val) / len(val)
            if datVal != 0:
                dd = 1
            else:
                dd = 0
                print "received data is 0 - Retry 10X to read data"
                de += 1
                if de > 10:
                    print "tried 10 times - giving up - taking 0 as valid data"
                    de = 0
                    dd = 1
            #print "nb avg: ", len(val), "value: ",datVal
        else:
            print "error - no values read. Retry."
            dd = 0
            de +=1
            if de > 10:
                print "tried 10 times - giving up - taking 0 as data"
                de = 0
                dd = 1
                
    #print "datVal: ", datVal    
    return datVal
        
        



     

#------Functions specific to grbl-Arduino--------------------------------
#waking-up Arduino
def startArduino(grblPort):
    global s
    gcode =  "$I"   #asking grbl for built info

    # Open serial port
    try:
        if s is None:
            s = serial.Serial(grblPort,grblbdr)
            s.timeout = 1
        else:
            if not s.isOpen():
                s = serial.Serial(grblPort,grblbdr)
                s.timeout = 1
    except NameError:
        s = serial.Serial(grblPort,grblbdr)
        s.timeout = 1

    # Wake up 
    s.write("\r\n\r\n") # Hit enter a few times to wake the Printrbot
    print "waking up arduino"
    time.sleep(1)   # Wait for Arduino to initialize
    s.flushInput()  # Flush startup text in serial input
    #sending string l to grbl
    s.write(gcode + '\n') # Send g-code block
    print "sent: ",gcode
    nb = s.inWaiting()
    #print "Nb Bytes: ",nb
    print "receiving response from arduino..",
    grbl_out = s.readline() # Wait for response - read only first line
    print ' : ' + grbl_out.strip()
    s.write('G91 F' + str(travelSpeed) + ' ')
    s.write('G01 X-1 \r \n')
    s.write('G01 X1 \r \n')
    time.sleep(1)
 
#sending G-code to Arduino
def sendCode(gcode):
    global s
    #print "grblPort: ", grblPort
    #print "sending code...", str(gcode)
    s.write(str(gcode))
    #print "code sent ", str(gcode)
    s.write('\r \n')
    time.sleep(0.05)

# closing serial port "s" to Arduino
def stopArduino():
    global s
    try:
        if s.isOpen():
            s.close()
            print "grblComPort is closed."
        else:
            print "s is already clsoed"
    except:
        print "error trying to close s"
    
    
    
#------End of grbl-Arduino--------------------------------


#+++++++++++++Functions specific to propeller-DataSpider++++++++++++++++

# functino nextMsgID() return Int a sequential message ID.
def nextMsgID(msgID):
    msgID = int(msgID + 1) & 255
    if msgID == 0:
        msgID = int(msgID + 1) & 255
    return msgID


def send(msgID, prop, key, value=None ):
    #""" sends a control packet with a message ID that corresponds to the string value 'key', with parameters specified in value.
    #key is a string that represents the message ID, or and int specifing the message ID.
    #value is either an integer, or a list of integers."""
    #i.e., to set data rate, value is a list of 2 numbers: the channel nb, and the rate

    if prop is None :
        print("send on bad port")
        return -1
    
    if key is None:
        print("send NoneType key", key)
        return -1

    try:
        msg = chr(key) + chr(nextMsgID(msgID))
        print "key is integer.... char: ", chr(key)
    except TypeError: # key is not an int. treat as string.         
        if key not in keyTable and key :
            print("Attempting invalid control msg ID", key)
            return -1
        msg = chr(keyTable.index(key)) + chr(nextMsgID(msgID))
        print "key index: ", keyTable.index(key), "char: ",chr(keyTable.index(key)) 

    if value is not None:
        #print "value: ", value
        try:
            for v in value:
                #print "value is a list"
                for n in range(4):
                    msg += chr( (v>>24-n*8)&255 )
                    #print "v:", v, "n: ", n, "add-msg: ", (v>>24-n*8)&255
        except TypeError: # value is not a list. treat as int.
            #print "value treated as integer"
            for n in range(4):
                msg += chr( (int(value)>>24-n*8)&255 )
                #print "n: ", n, "add-msg: ", (int(value)>>24-n*8)&255
    msg = msg.replace(ESC, ESC+ESC)
    msg = msg.replace(EOP, ESC+EOP)
    chksum = 0
    for c in msg:
        chksum = ((chksum<<1) | (chksum>>7)) & 255 # left-rotate
        chksum = (chksum + ord(c)) % 256           # 8-bit addition

    msg = msg + EOP + chr(chksum) #completing the message with EOP + chksum

    try:
        retv = prop.write(msg)
    except (serial.serialutil.portNotOpenError, ValueError, serial.serialutil.SerialTimeoutException) as err:
        print("Writing to closed port", err)
        return -1
    except serial.SerialException as err:
        print("SerialException on write", err)
        return -1
    #self.comlock.release()
    return 1 

def startADC(port,bdr,chan,rate):
    global prop
    val = [chan,rate]
    print "starting ADC"
    #print "values: ", val
    #print "propcomport: ", port
    
    try:
        if prop is None:
            prop = serial.Serial(port,bdr)
            prop.timeout = 0.5
        else:
            if not prop.isOpen():
                prop = serial.Serial(port,bdr)
                prop.timeout = 0.5
    except NameError:
        prop = serial.Serial(port,bdr)
        prop.timeout = 0.5

    ttt = send(msgID, prop,'set',val)  #setting rate
    if ttt != 1:
        print "failure...."
    ttt = send(nextMsgID(msgID), prop,'start',2**chan)  #start ADC
    time.sleep(0.2)      #allow some time for the prop-chip to respond

def stopADC(chan):
    global prop
    ttt = send(nextMsgID(msgID), prop,'stop',2**chan)  #start ADC
    try:
        if prop.isOpen():
            prop.close()
            print "propComPort is now closed."
        else:
            print "prop is already clsoed"
    except:
        print "error trying to close prop"

#+++++++++++++End Of propeller-DataSpider Functions++++++++++++++++++++



#helper function -------
def scale_bitmap(bitmap, width, height):
    image = wx.ImageFromBitmap(bitmap)
    image = image.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
    result = wx.BitmapFromImage(image)
    return result


def saveData(frame,header):
    global data, dataInput, imgData, totalTravel, duration, travelStep

    #travelStep = dataInput[1]
    #duration = dataInput[4]
    npts = int(totalTravel / travelStep) + 1
    #imgData = img[:npts,:npts]
    #print "save function - header: ", header
    #print "size of array",imgData.size
    
    
    if imgData.size > 0:
        filetypes = "CSV files (*.csv)|*.csv|Text files (*.txt)|*.txt|All files|*"
        dlg = wx.FileDialog(frame,"Choose a file", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT, wildcard=filetypes)
        outFile = None
        if dlg.ShowModal()==wx.ID_OK:
            try:
                filename=dlg.GetFilename()
                dirname=dlg.GetDirectory()
                fullPath = os.path.join(dirname, filename)
                date = '"' + time.asctime() + '"'
                title = "saving data"
                #SetTitle( title + " - " + filename )
                outFile = open(fullPath, "w")
                # write header info
                outFile.write( date )
                outFile.write( "\n" )
                outFile.write( '"' + header + '"' )
                outFile.write( "\n" )
                outFile.write( "Step:," + str(travelStep) )
                outFile.write( ",Duration:," + str(duration) )
                outFile.write( "\n" )
                
                # write data
                nData = int(npts)
                for n in range(nData):
                    strfmt = ""
                    for nn in range(nData):
                        try:
                            if nn == nData - 1:
                                strfmt = strfmt + str(imgData[n,nn]) + "\n"
                            else:
                                strfmt = strfmt + str(imgData[n,nn]) + ","
                        except IndexError:
                            print "index error"
                            pass
                    outFile.write(strfmt)
                outFile.close()
                #print "finished writing data in file"

                
            except IOError as e:
                print "Error opening file", e
            except ValueError as e:
                print "Error writing file", e
            except:
                print "Error in saving data"
                outFile.close()
                
        dlg.Destroy()











################# Starts Main Here #######################    
def main():

    # make GUI
    app = wx.PySimpleApp()
    frame = MyFrame(None, title, xSize, ySize, panelWidth)

    # setup complete, show frame. 
    frame.Show()
    app.MainLoop()


# start program
main()



