#!/usr/bin/python
# -*- coding: latin-1*-

import six

try:
    from PyQt5.Qt import QCheckBox, Qt, QHBoxLayout, QIcon
except ImportError:
    from PyQt4.Qt import QCheckBox, Qt, QHBoxLayout, QIcon

from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.gui2 import info_dialog
from calibre.utils.config import JSONConfig

plugin_prefs = JSONConfig('plugins/Babelio')
plugin_prefs.defaults['cover'] = True

class ConfigWidget(DefaultConfigWidget):

    def __init__(self, plugin):
        DefaultConfigWidget.__init__(self, plugin)
        self.hl = QHBoxLayout()
        self.cb = QCheckBox('Télécharger la couverture')
        self.cb.setChecked(plugin_prefs['cover'])
        self.hl.addWidget(self.cb, alignment=Qt.AlignHCenter)
        self.l.addLayout(self.hl, 2, 0)
        self.cb.stateChanged.connect(self.commit_true)

    def commit_true(self):
        DefaultConfigWidget.commit(self)
        plugin_prefs['cover'] = self.cb.checkState() == Qt.Checked
        # return self.restart()

    def commit(self):
        DefaultConfigWidget.commit(self)

    def prompt_for_restart(self, title, message):
        d = info_dialog(self, title, message, show_copy_button=False)
        b = d.bb.addButton(_('Restart calibre now'), d.bb.AcceptRole)
        b.setIcon(QIcon(I('lt.png')))
        d.do_restart = False
        def rf():
            d.do_restart = True
        b.clicked.connect(rf)
        d.set_details('')
        d.exec_()
        b.clicked.disconnect()
        return d.do_restart


    def restart(self):

        restart = self.prompt_for_restart('Settings changed',
                           '<p>Settings for this plugin in this library have been changed.</p>'
                           '<p>Please restart calibre now.</p>')
        self.close()
        if restart:
            self.gui.quit(restart=True)


