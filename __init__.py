# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ProjFactors
                                 A QGIS plugin
 Visualise distortions in map projection
                             -------------------
        begin                : 2014-12-18
        copyright            : (C) 2014 by Drazen Tutic
        email                : dtutic@geof.hr
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load ProjFactors class from file ProjFactors.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .proj_factors import ProjFactors
    return ProjFactors(iface)