from abc import ABCMeta, abstractmethod

import wx

import gui.globalEvents as GE
import gui.mainFrame
from gui.contextMenu import ContextMenuUnconditional
from service.settings import WorstCaseEhpSettings

_t = wx.GetTranslation


class ToggleWorstCaseEhp(ContextMenuUnconditional, metaclass=ABCMeta):

    def __init__(self):
        self.mainFrame = gui.mainFrame.MainFrame.getInstance()
        self.settings = WorstCaseEhpSettings.getInstance()

    @property
    @abstractmethod
    def optionName(self):
        raise NotImplementedError()

    def display(self, callingWindow, srcContext):
        return srcContext == "worstCaseEhpViewFull"

    def activate(self, callingWindow, fullContext, i):
        self.settings.set(self.optionName, not self.settings.get(self.optionName))
        fitID = self.mainFrame.getActiveFit()
        wx.PostEvent(self.mainFrame, GE.FitChanged(fitIDs=(fitID,)))

    def isChecked(self, i):
        return self.settings.get(self.optionName)


class FactorDamageWorstCaseEhp(ToggleWorstCaseEhp):
    optionName = 'includeDamage'

    def getText(self, callingWindow, itmContext):
        return _t('Factor in Damage')


class T1WorstCaseEhp(ToggleWorstCaseEhp):
    optionName = 't1'

    def getText(self, callingWindow, itmContext):
        return _t('T1 Ammo')


class T2WorstCaseEhp(ToggleWorstCaseEhp):
    optionName = 't2'

    def getText(self, callingWindow, itmContext):
        return _t('T2 Ammo')


class NavyWorstCaseEhp(ToggleWorstCaseEhp):
    optionName = 'faction'

    def getText(self, callingWindow, itmContext):
        return _t('Navy Ammo')


class OfficerWorstCaseEhp(ToggleWorstCaseEhp):
    optionName = 'officer'

    def getText(self, callingWindow, itmContext):
        return _t('Officer Ammo')


FactorDamageWorstCaseEhp.register()
T1WorstCaseEhp.register()
NavyWorstCaseEhp.register()
T2WorstCaseEhp.register()
OfficerWorstCaseEhp.register()
