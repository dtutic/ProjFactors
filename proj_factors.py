# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ProjFactors
                                 A QGIS plugin
 Visualise distortions in map projection
                              -------------------
        begin                : 2014-12-18
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Drazen Tutic, Viktoria Duracic
        email                : dtutic@geof.hr, viktoria.duracic@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QFileInfo
from PyQt4.QtGui import QAction, QIcon, QColor, QFileDialog
import resources_rc
from proj_factors_dialog import ProjFactorsDialog
import os, os.path
from qgis.core import *
from osgeo import gdal, osr, ogr
import math, array
#import qgis.gui
from subprocess import Popen, PIPE
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox

class ProjFactors:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'ProjFactors_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = ProjFactorsDialog()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Projection Factors')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'ProjFactors')
        self.toolbar.setObjectName(u'ProjFactors')
        self.crs_proj4_list = None      
        self.prepare()


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('ProjFactors', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/ProjFactors/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Map Projection Factors'),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&Projection Factors'), action)
            self.iface.removeToolBarIcon(action)

    def selectFile(self):
        filename = QFileDialog.getSaveFileName(self.dlg, "Save as GeoTIFF", "", 'TIFF (*.tif *.tiff);;All Files (*)')
        if not filename.lower().endswith(('.tif', '.tiff')):
            filename = filename+'.tif'
        self.dlg.input_filename.setText(filename)

    def factorChanged(self):
        factor = self.dlg.factor_selected.currentIndex()
        # 0=Meridian scale, 1=Parallel scale, 2=Areal scale, 6=Max scale, 7=Min scale
        if factor == 0 or factor == 1 or factor == 2 or factor == 6 or factor == 7: 
            self.dlg.label_units.setText('Value:')
            self.dlg.units_scale.show()
            self.dlg.units_angle.hide()                
        else: # Angles
            self.dlg.label_units.setText('Units:')
            self.dlg.units_scale.hide()
            self.dlg.units_angle.show()                

    def regionChanged_layer(self): 
        flag = self.dlg.check_layer.isChecked()
        self.dlg.input_bbox.setEnabled(not flag)
        self.dlg.layer_selected.setEnabled(flag)
        self.dlg.check_bbox.setChecked(not flag)
        if flag: 
            self.updateRegion_from_layer()

    def regionChanged_bbox(self): 
        flag = self.dlg.check_bbox.isChecked() 
        self.dlg.input_bbox.setEnabled(flag)
        self.dlg.layer_selected.setEnabled(not flag)
        self.dlg.check_layer.setChecked(not flag)
        if not flag:
            self.updateRegion_from_layer()

    def sizeChanged_raster(self): 
        flag = self.dlg.check_raster_size.isChecked()
        self.dlg.input_pixel_size.setEnabled(not flag)
        self.dlg.input_raster_size.setEnabled(flag)
        self.dlg.check_pixel_size.setChecked(not flag)

    def sizeChanged_pixel(self): 
        flag = self.dlg.check_pixel_size.isChecked()
        self.dlg.input_pixel_size.setEnabled(flag)
        self.dlg.input_raster_size.setEnabled(not flag)
        self.dlg.check_raster_size.setChecked(not flag)

    def parseCrs(self,crsDest): # create geographic CRS from current projected CRS using proj4 definition
        parm = crsDest.toProj4().split(' ')
        crs = '+proj=longlat '
        for item in parm:
            text = item.encode('latin-1')
            if text.find('+a') == 0:
                crs = crs + item + ' '         
            if text.find('+b') == 0:
                crs = crs + item + ' '         
            if text.find('+towgs') == 0:
                crs = crs + item + ' '         
            if text.find('+ellps') == 0:
                crs = crs + item + ' '         
            if text.find('+no_defs') == 0:
                crs = crs + item + ' '         
            if text.find('+datum') == 0:
                crs = crs + item + ' '         
        crsSrc = QgsCoordinateReferenceSystem()
        try:
            crsSrc.createFromProj4(crs)
            return crsSrc
        except:
            pass
        else:
            self.iface.messageBar().pushMessage("Error", "Invalid geographic coordinate system: "+crs, level=QgsMessageBar.CRITICAL, duration=10)

    def setProjectionTransform(self):
        try:
            crsDest = self.iface.mapCanvas().mapSettings().destinationCrs()
        except:
            crsDest = self.iface.mapCanvas().mapRendered().destinationCrs()
        if crsDest.isValid() and not crsDest.geographicFlag() and crsDest.projectionAcronym() != 'geocent':
            try:
                crsSrc = QgsCoordinateReferenceSystem(crsDest.geographicCRSAuthId()) 
            except:
                pass        
            else:
                crsSrc = self.parseCrs(crsDest)
            if crsSrc.isValid():
                return crsSrc,crsDest
        else:
            self.iface.messageBar().pushMessage("Error", "Project CRS should not be geographic or geocentric!", level=QgsMessageBar.CRITICAL, duration=10)

    def updateRegion_from_layer(self):
        try:
            layer = self.dlg.layer_selected.itemData(self.dlg.layer_selected.currentIndex())
            extent = layer.extent()		
            #if layer is not in geographic CRS, transform it to one and find extent
            if not layer.crs().geographicFlag():
                crsSrc, crsDest = self.setProjectionTransform()
                coordTransform = QgsCoordinateTransform(layer.crs(), crsSrc)
                bb = QgsGeometry.fromRect(extent)
                bb.transform(coordTransform)
                extent = bb.boundingBox()	
            x_min = extent.xMinimum()
            x_max = extent.xMaximum()
            y_min = extent.yMinimum()
            y_max = extent.yMaximum()
            if y_max > 89: y_max = 89
            if y_min < -89: y_min = -89
            if x_max > 179: x_max = 179
            if x_min < -179: x_min = -179
            self.dlg.input_bbox.setText(str(y_max)+','+str(y_min)+','+str(x_min)+','+str(x_max))
        except:
            self.dlg.input_bbox.setText('89,-89,-179,179')
        self.updateSize()

    def isf(self, input):
        try:
            num = float(input)
        except ValueError:
            return False
        return True

    def updateSize(self):
        self.dlg.button_box.button(0x02000000).setEnabled(False)
        bbox = self.dlg.input_bbox.text().split(',')
        if len(bbox) == 4 and self.isf(bbox[0]) and self.isf(bbox[1]) and self.isf(bbox[2]) and self.isf(bbox[3]):
            y_max = float(bbox[0])
            y_min = float(bbox[1])
            x_min = float(bbox[2])
            x_max = float(bbox[3])
            x_res = -1
            y_res = -1
            pixel_size_x = -1
            pixel_size_y = -1
            if self.dlg.check_raster_size.isChecked():
                if self.dlg.input_raster_size.text().count(',') == 1:
                    res = self.dlg.input_raster_size.text().split(',')
                    try:
                        x_res = int(res[0])
                        pixel_size_x = (x_max - x_min) / float(x_res)
                    except (ValueError, ZeroDivisionError):
                        self.dlg.input_raster_size.setFocus()
                        return
                    if res[1] != '':
                        try:                
                            y_res = int(res[1])
                            pixel_size_y = (y_max - y_min) / float(y_res)
                        except (ValueError, ZeroDivisionError):
                            self.dlg.input_raster_size.setFocus()
                            return
                    else:
                        pixel_size_y = pixel_size_x
                        y_res = int((y_max - y_min) / pixel_size_y)                    
                    self.dlg.input_pixel_size.setText(str(pixel_size_x)+','+str(pixel_size_y))
                    self.dlg.button_box.button(0x02000000).setEnabled(True)
                    return x_min, x_max, y_min, y_max, x_res, y_res, pixel_size_x, pixel_size_y
                elif self.dlg.input_raster_size.text().count(',') == 0:
                    try:
                        x_res = int(self.dlg.input_raster_size.text())
                        pixel_size_x = (x_max - x_min) / float(x_res)
                        pixel_size_y = pixel_size_x
                        y_res = int((y_max - y_min) / pixel_size_y)                    
                        self.dlg.input_raster_size.setText(str(x_res))
                        self.dlg.input_pixel_size.setText(str(pixel_size_x))
                        self.dlg.button_box.button(0x02000000).setEnabled(True)
                        return x_min, x_max, y_min, y_max, x_res, y_res, pixel_size_x, pixel_size_y
                    except (ValueError, ZeroDivisionError):
                        self.dlg.input_raster_size.setFocus()
                        return
                else:
                    self.dlg.input_raster_size.setFocus()
                    return
            else:
                if self.dlg.input_pixel_size.text().count(',') == 1:
                    res = self.dlg.input_pixel_size.text().split(',')
                    try:
                        pixel_size_x = float(res[0])
                    except ValueError:
                        self.dlg.input_pixel_size.setFocus()
                        return   
                    if res[1] != '':
                        try:                
                            pixel_size_y = float(res[1])
                        except ValueError:
                            self.dlg.input_pixel_size.setFocus()
                            return
                    else:
                        pixel_size_y = pixel_size_x
                    try:
                        x_res = int((x_max - x_min) / pixel_size_x)        
                        y_res = int((y_max - y_min) / pixel_size_y)        
                    except ZeroDivisionError:
                        self.dlg.input_pixel_size.setFocus()
                        return
                    self.dlg.input_raster_size.setText(str(x_res) + ',' + str(y_res))
                    self.dlg.button_box.button(0x02000000).setEnabled(True)
                    return x_min, x_max, y_min, y_max, x_res, y_res, pixel_size_x, pixel_size_y
                elif self.dlg.input_pixel_size.text().count(',') == 0:
                    try:
                        pixel_size_x = float(self.dlg.input_pixel_size.text())
                        x_res = int((x_max - x_min) / pixel_size_x)        
                        y_res = int((y_max - y_min) / pixel_size_x)
                        pixel_size_y = pixel_size_x
                        self.dlg.input_raster_size.setText(str(x_res) + ',' + str(y_res))
                        return x_min, x_max, y_min, y_max, x_res, y_res, pixel_size_x, pixel_size_y
                    except (ValueError, ZeroDivisionError):
                        self.dlg.input_pixel_size.setFocus()            
                        return         
                else:
                    self.dlg.input_pixel_size.setFocus()            

    def units(self,factor):
        # TODO: write scales as percents
        if factor == 1: # scale factor is calculated
            if self.dlg.units_scale.currentIndex() == 0: # scale
                return 1.0
            elif self.dlg.units_scale.currentIndex() == 1: # distortion = scale -1
                return -1.0
            elif self.dlg.units_scale.currentIndex() == 2: # scale * 1000 
                return 1000.0
            elif self.dlg.units_scale.currentIndex() == 3: # distortion * 1000 
                return -1000.0
        else: # angle factor is calculated
            if self.dlg.units_angle.currentIndex() == 0: # degrees
                return 180.0 / math.pi
            elif self.dlg.units_angle.currentIndex() == 1: # radians
                return 1.0

    def get_meridian_scale(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:9] == 'Meridian ':
              row.append(float(line[21:31]))
        return row

    def get_parallel_scale(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:3] == 'Par':
             row.append(float(line[21:31]))
        return row

    def get_areal_scale(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:3] == 'Are':
             row.append(float(line[21:31]))
        return row

    def get_convergence(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:3] == 'Con':
             row.append(float(line[-13:-2]) * math.pi / 180.0)
        return row

    def get_meridian_parallel_angle(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:9] == 'Meridian/':
             row.append(float(line[25:33]) * math.pi / 180.0)
        return row

    def get_angular_distortion(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:3] == 'Ang':
             row.append(float(line[24:29]) * math.pi / 180.0)
        return row

    def get_max_scale(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:3] == 'Max':
             row.append(float(line[39:45]))
        return row

    def get_min_scale(self, coord):
        row = array.array('d')
        sub_proj = Popen(self.crs_proj4_list, bufsize = -1, stdout = PIPE, stdin = PIPE, stderr = PIPE)
        factors = sub_proj.communicate(input = coord)[0].split('\n')
        for line in factors:
          if line[0:3] == 'Max':
             row.append(float(line[47:53]))
        return row
        

    def generateFactor(self):        
        crsSrc, crsDest = self.setProjectionTransform()
        print 'New raster coordinate system: ',
        print crsSrc
        print 'Project coordinate system: ',
        print crsDest
        transform = QgsCoordinateTransform(crsSrc, crsDest)
        x_min, x_max, y_min, y_max, x_res, y_res, pixel_size_x, pixel_size_y = self.updateSize() 
        NoData_value = -9999
        target_ds = gdal.GetDriverByName('GTiff').Create(self.dlg.input_filename.text(), x_res, y_res, 1, gdal.GDT_Float32)
        target_ds.SetGeoTransform((x_min, pixel_size_x, 0, y_max, 0, -pixel_size_y))
        band = target_ds.GetRasterBand(1)
        band.SetNoDataValue(NoData_value)
        rasterData = band.ReadAsArray(0, 0, x_res, y_res)

        step_x = pixel_size_x * math.pi / 180
        step_y = pixel_size_y * math.pi / 180
        fi = (y_min + 0.5 * pixel_size_y) * math.pi / 180.0
        
        self.dlg.progressBar.setRange(0,y_res)                
        # We have to use proj as an external process and parse the output
        # This block works only with customized QgsCoordinateTransform class
        # with added functions for projection factors
        # This would be better, faster and more precise solution that
        # reqires adding this feature to QGIS QgsCoordinateTransform class
        #try:
        #  if self.dlg.factor_selected.currentText() == 'Meridian scale':
        #      methodToCall = getattr(transform, 'get_meridian_scale') 
        #      unit = self.units(1)
        #  elif self.dlg.factor_selected.currentText() == 'Parallel scale':
        #      methodToCall = getattr(transform, 'get_parallel_scale') 
        #      unit = self.units(1)
        #  elif self.dlg.factor_selected.currentText() == 'Aeral scale':
        #      methodToCall = getattr(transform, 'get_areal_scale') 
        #      unit = self.units(1)
        #  elif self.dlg.factor_selected.currentText() == 'Meridian convergence':
        #      methodToCall = getattr(transform, 'get_convergence') 
        #      unit = self.units(0)
        #  elif self.dlg.factor_selected.currentText() == 'Meridian-parallel angle':
        #      methodToCall = getattr(transform, 'get_meridian_parallel_angle') 
        #      unit = self.units(0)
        #  elif self.dlg.factor_selected.currentText() == 'Angle distortion':
        #      methodToCall = getattr(transform, 'get_angular_distortion') 
        #      unit = self.units(0)
        #  elif self.dlg.factor_selected.currentText() == 'Max linear scale':
        #      methodToCall = getattr(transform, 'get_max_scale') 
        #      unit = self.units(1)
        #  elif self.dlg.factor_selected.currentText() == 'Min linear scale':
        #      methodToCall = getattr(transform, 'get_min_scale') 
        #      unit = self.units(1)              
        #  for j in xrange(0,y_res):
        #      la = (0.5 * pixel_size_x + x_min) * math.pi / 180.0                
        #      for i in xrange(0, x_res):
        #          if unit > 0:
        #              rasterData[j,i] = methodToCall(la, fi) * unit
        #          else:
        #              if unit == -1:
        #                  rasterData[j,i] = methodToCall(la, fi) - 1.0
        #              elif unit == -1000:
        #                  rasterData[j,i] = (methodToCall(la, fi) - 1.0) * 1000.0
        #          la += step_x
        #      fi += step_y
        #      self.dlg.progressBar.setValue(j + 1)                         
        #except:

        # proj.exe which comes with QGIS in Windows usually gives error with -V option
        # so we need our own compiled version for Windows systems
        if os.name == 'nt':
            proj_bin = os.path.dirname(os.path.abspath(__file__)) + '\proj.exe '
        else:
            proj_bin = 'proj '    
        self.crs_proj4_list = (proj_bin + crsDest.toProj4().encode('latin-1') + ' -V').split(' ') 
        
        if self.dlg.factor_selected.currentText() == 'Meridian scale':
            methodToCall = getattr(self, 'get_meridian_scale') 
            unit = self.units(1)
        elif self.dlg.factor_selected.currentText() == 'Parallel scale':
            methodToCall = getattr(self, 'get_parallel_scale') 
            unit = self.units(1)
        elif self.dlg.factor_selected.currentText() == 'Aeral scale':
            methodToCall = getattr(self, 'get_areal_scale') 
            unit = self.units(1)
        elif self.dlg.factor_selected.currentText() == 'Meridian convergence':
            methodToCall = getattr(self, 'get_convergence') 
            unit = self.units(0)
        elif self.dlg.factor_selected.currentText() == 'Meridian-parallel angle':
            methodToCall = getattr(self, 'get_meridian_parallel_angle') 
            unit = self.units(0)
        elif self.dlg.factor_selected.currentText() == 'Angle distortion':
            methodToCall = getattr(self, 'get_angular_distortion') 
            unit = self.units(0)     
        elif self.dlg.factor_selected.currentText() == 'Max linear scale':
            methodToCall = getattr(self, 'get_max_scale') 
            unit = self.units(1)
        elif self.dlg.factor_selected.currentText() == 'Min linear scale':
            methodToCall = getattr(self, 'get_min_scale') 
            unit = self.units(1)
             
        for j in xrange(0, y_res):
            la = (0.5 * pixel_size_x + x_min) * math.pi / 180.0  
            coord = ''
            for i in xrange(0, x_res):
                coord = coord + str(la * 180.0 / math.pi) + ' ' + str(fi * 180.0 / math.pi) + ('\n')
                la += step_x
            row = methodToCall(coord)
            for i in xrange(0, x_res):
                if unit>0:
                    rasterData[j,i] = row[i] * unit
                else:
                    if unit == -1:
                        rasterData[j,i] = row[i] - 1.0
                    elif unit == -1000:
                        rasterData[j,i] = (row[i] - 1.0) * 1000.0
            fi += step_y
            self.dlg.progressBar.setValue(j + 1)        
          
        self.dlg.progressBar.setValue(0)        
        reversed_arr = rasterData[::-1]
        band.WriteArray(reversed_arr)
        target_ds.SetProjection(crsSrc.toWkt().encode('latin-1')) 
        band.FlushCache()
        target_ds = None

        if self.dlg.check_add_result.isChecked():
            fileInfo = QFileInfo(self.dlg.input_filename.text())
            baseName = fileInfo.baseName()
            rlayer = QgsRasterLayer(self.dlg.input_filename.text(), baseName)
            if not rlayer.isValid():
                self.iface.messageBar().pushMessage("Error", "Raster layer failed to load!", level=QgsMessageBar.CRITICAL, duration=5)
            else:
				# Code from here to the end of this function is written by Viktoria Đuračić,
                # student at University of Zagreb, Faculty of Geodesy, 2018			
                
                # This part loads created raster and applies default style to it
                provider = rlayer.dataProvider()
                stats = provider.bandStatistics(1, QgsRasterBandStats.All)
                vmin = stats.minimumValue
                vmax = stats.maximumValue   
                if vmax - vmin > 0.00001: #apply colors only if projection factor is not constant to obtained accuracy
                    v25 = vmin + (vmax - vmin) * 0.25
                    v50 = (vmax + vmin) * 0.5
                    v75 = vmin + (vmax - vmin) * 0.75
                    s = QgsRasterShader()
                    c = QgsColorRampShader()
                    c.setColorRampType(QgsColorRampShader.INTERPOLATED)
                    i = []
                    i.append(QgsColorRampShader.ColorRampItem(vmin, QColor('#2b83ba'), str(vmin))) 
                    i.append(QgsColorRampShader.ColorRampItem(v25, QColor('#abdda4'), str(v25)))
                    i.append(QgsColorRampShader.ColorRampItem(v50, QColor('#ffffbf'), str(v50)))
                    i.append(QgsColorRampShader.ColorRampItem(v75, QColor('#fdae61'), str(v75)))
                    i.append(QgsColorRampShader.ColorRampItem(vmax, QColor('#d7191c'), str(vmax))) 
                    c.setColorRampItemList(i)
                    s.setRasterShaderFunction(c)
                    ps = QgsSingleBandPseudoColorRenderer(rlayer.dataProvider(), 1, s)
                    rlayer.setRenderer(ps)              
                QgsMapLayerRegistry.instance().addMapLayer(rlayer)              
                
                # This part creates isolines (if possible) from raster and saves it in ESRI shapefile
                try:
                    contour_interval = math.pow(10, math.floor(math.log10((vmax - vmin) / 10))) * 2
                except ValueError:
                    self.iface.messageBar().pushMessage("Info", "Calculated factor is probably constant for this map projection.", level=QgsMessageBar.INFO, duration=10)
                    return 
                srs = osr.SpatialReference()
                srs.ImportFromWkt(crsSrc.toWkt().encode('latin-1'))                
                vpath = os.path.dirname(os.path.abspath(self.dlg.input_filename.text()))
                vfile = os.path.join(vpath, baseName + "_isolines.shp")
               
                ogr_ds = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(vfile)
                ogr_lyr = ogr_ds.CreateLayer("isolines", srs, ogr.wkbLineString)
                ogr_lyr.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
                ogr_lyr.CreateField(ogr.FieldDefn("projfact", ogr.OFTReal))
                tif_dataset = gdal.Open(self.dlg.input_filename.text(), gdal.GA_ReadOnly)
                band = 1
                gdal.ContourGenerate(tif_dataset.GetRasterBand(band),
                                 contour_interval,
                                 0, #contour base
                                 [], #fixed level list
                                 0, #use no data flag
                                 -9999, #no data value
                                 ogr_lyr,
                                 0, #id field
                                 1) #projfact field
                ogr_ds = None

                # Add created isolines to QGIS project and apply default style and labels
                clayer = QgsVectorLayer(vfile, baseName+"_isolines", "ogr")
                QgsMapLayerRegistry.instance().addMapLayer(clayer)
                
                symbols = clayer.rendererV2().symbols2(QgsRenderContext())
                symbol = symbols[0]
                symbol.setColor(QColor.fromRgb(0, 0, 0))

                label = QgsPalLayerSettings()
                label.readFromLayer(clayer)
                label.enabled = True
                label.mergeLines = True
                label.minFeatureSize = 10
                label.fieldName="projfact"
                label.placement= QgsPalLayerSettings.Line
                label.setDataDefinedProperty(QgsPalLayerSettings.Size, True, True, "8", "")
                label.decimals = 4
                label.formatNumbers = True
                label.writeToLayer(clayer)        

    def prepare(self):
        self.updateDialog()
        # Default raster width is 1000px, calculate pixel size from that and set it active
        self.sizeChanged_raster()
        self.updateSize()
        # Connect dialog signals to methods
        self.dlg.browse_file.clicked.connect(self.selectFile) # select file to save raster data in TIF
        self.dlg.factor_selected.currentIndexChanged.connect(self.factorChanged) # factor is changed
        self.dlg.check_layer.stateChanged.connect(self.regionChanged_layer) # region from layer
        self.dlg.check_bbox.stateChanged.connect(self.regionChanged_bbox) # region from bbox
        self.dlg.check_raster_size.stateChanged.connect(self.sizeChanged_raster) # raster size defined by width and height
        self.dlg.check_pixel_size.stateChanged.connect(self.sizeChanged_pixel) # raster size defined by pixel size
        self.dlg.layer_selected.currentIndexChanged.connect(self.updateRegion_from_layer) # layer for region is changed
        self.dlg.input_bbox.textEdited.connect(self.updateSize) # manual entry of region
        self.dlg.input_raster_size.textEdited.connect(self.updateSize) # manual entry of raster size
        self.dlg.input_pixel_size.textEdited.connect(self.updateSize) # manual entry of pixel size
        self.dlg.button_box.button(0x02000000).clicked.connect(self.generateFactor) # connect Apply button to main process

    def updateDialog(self):
        self.dlg.layer_selected.clear()
        layers = QgsMapLayerRegistry.instance().mapLayers().values()
        for layer in layers:
            self.dlg.layer_selected.addItem( layer.name(), layer )
        # If there are loaded layers, calculate region from selected layer
        if self.dlg.layer_selected.currentIndex() != -1:        
            self.updateRegion_from_layer()
            self.regionChanged_layer()
        # Set default region to world, it is usually good to avoid poles and cutting meridian
        # User should define valid region for projection selected
        # TODO: Warn users with valid region for selected projection
        else:
            self.dlg.input_bbox.setText('89,-89,-179,179')
            self.dlg.check_bbox.setChecked(True)
            self.dlg.check_layer.setChecked(False)
            self.regionChanged_bbox()		
        self.updateSize()   

    def run(self):
        self.dlg.setModal(False)
        self.updateDialog()
        self.dlg.show()
