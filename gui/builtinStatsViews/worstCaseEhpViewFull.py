# =============================================================================
# Copyright (C) 2010 Diego Duclos
#
# This file is part of pyfa.
#
# pyfa is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyfa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyfa.  If not, see <http://www.gnu.org/licenses/>.
# =============================================================================

import re
from collections import OrderedDict

# noinspection PyPackageRequirements
import wx

import gui.mainFrame
from eos.saveddata.damagePattern import DamagePattern
from eos.saveddata.module import Module
from gui.bitmap_loader import BitmapLoader
from gui.statsView import StatsView
from gui.utils.numberFormatter import formatAmount
from service.ammo import Ammo
from service.fit import Fit
from service.market import Market
from service.settings import WorstCaseEhpSettings

_t = wx.GetTranslation


# Each weapon system is represented by a T2 module, as only T2 modules accept both
# T1/faction and T2 charges. Damage ratios do not change with charge size, so
# medium sized modules are used where available
WEAPONS = OrderedDict([
    ('autocannon', ('Autocannon', (2913,))),  # 425mm AutoCannon II
    ('artillery', ('Artillery', (2969,))),  # 720mm Howitzer Artillery II
    ('vorton', ('Vorton Projector', (54748,))),  # Medium Vorton Projector II
    # Short range missiles, long range missiles and bombs all use different charges
    ('missile', ('Missiles', (
        25715,  # Heavy Assault Missile Launcher II
        2410,  # Heavy Missile Launcher II
        4256,  # Bomb Launcher II
    ))),
])

# Every charge of these weapons deals a single damage type, so all charges of the same damage type
# tie and we show the damage type instead of a charge
DAMAGE_TYPE_WEAPONS = {
    'missile': {
        "em": "EM",
        "thermal": "Thermal",
        "kinetic": "Kinetic",
        "explosive": "Explosive"
    },
}

# Charge size suffix, e.g. the " M" in "Republic Fleet EMP M"
CHARGE_SIZE_SUFFIX = re.compile(r' (S|M|L|XL)$')

# 'faction' is navy faction ammo, 'officer' is high-tier pirate faction ammo like Domination or True Sansha,
# split the same way as in the application profile graph
TIERS = ('t1', 't2', 'faction', 'officer')


class WorstCaseEhpViewFull(StatsView):
    name = "worstCaseEhpViewFull"

    def __init__(self, parent):
        StatsView.__init__(self)
        self.parent = parent
        self._cachedValues = []
        self._chargeCache = {}
        self.activeFit = None
        self.settings = WorstCaseEhpSettings.getInstance()
        self.mainFrame = gui.mainFrame.MainFrame.getInstance()

    def getHeaderText(self, fit):
        return _t("Worst Case EHP")

    def getTextExtentW(self, text):
        width, height = self.parent.GetTextExtent(text)
        return width

    def populatePanel(self, contentPanel, headerPanel):
        contentSizer = contentPanel.GetSizer()
        self.panel = contentPanel

        self.headerPanel = headerPanel

        # Weapon selection
        weaponSizer = wx.BoxSizer(wx.HORIZONTAL)
        contentSizer.Add(weaponSizer, 0, wx.EXPAND | wx.BOTTOM, 3)

        self.weaponChoice = wx.Choice(contentPanel, wx.ID_ANY,
                                      choices=[_t(label) for label, typeIDs in WEAPONS.values()])
        self.weaponChoice.SetToolTip(wx.ToolTip(_t("Weapon system you are being shot by")))
        selectedWeapon = self.settings.get('weapon')
        if selectedWeapon not in WEAPONS:
            selectedWeapon = next(iter(WEAPONS))
        self.weaponChoice.SetSelection(list(WEAPONS).index(selectedWeapon))
        self.weaponChoice.Bind(wx.EVT_CHOICE, self.OnWeaponChange)
        weaponSizer.Add(self.weaponChoice, 1, wx.ALIGN_CENTER_VERTICAL)

        # Ammo tier selection is done via the panel's context menu, see worstCaseEhpOptions

        # Display table
        sizerEhp = wx.FlexGridSizer(2, 4, 0, 0)
        for i in range(4):
            sizerEhp.AddGrowableCol(i)
        contentSizer.Add(sizerEhp, 0, wx.EXPAND, 0)

        # first row is for icons
        toolTipText = {
            "shield": _t("Shield"),
            "armor": _t("Armor"),
            "hull": _t("Hull")
        }
        for tankType in ("shield", "armor", "hull"):
            bitmap = BitmapLoader.getStaticBitmap("%s_big" % tankType, contentPanel, "gui")
            tooltip = wx.ToolTip(toolTipText[tankType])
            bitmap.SetToolTip(tooltip)
            sizerEhp.Add(bitmap, 0, wx.ALIGN_CENTER)
        sizerEhp.Add(wx.StaticText(contentPanel, wx.ID_ANY, _t("EHP")), 0, wx.ALIGN_CENTER)

        # second row is for the damage-adjusted EHP against the worst case ammo
        for tankType in ("shield", "armor", "hull", "total"):
            label = wx.StaticText(contentPanel, wx.ID_ANY, "0")
            setattr(self, "labelEhp%s" % tankType.capitalize(), label)
            sizerEhp.Add(label, 0, wx.ALIGN_CENTER)

        # Worst case ammo
        ammoSizer = wx.BoxSizer(wx.HORIZONTAL)
        contentSizer.Add(ammoSizer, 0, wx.EXPAND | wx.TOP, 3)

        self.bitmapWorstAmmo = wx.StaticBitmap(contentPanel)
        ammoSizer.Add(self.bitmapWorstAmmo, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        self.labelWorstAmmo = wx.StaticText(contentPanel, wx.ID_ANY, "")
        ammoSizer.Add(self.labelWorstAmmo, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)

        # damage split of the worst case ammo, only damage types it actually deals are shown
        toolTipText = {
            "em": _t("EM damage"),
            "thermal": _t("Thermal damage"),
            "kinetic": _t("Kinetic damage"),
            "explosive": _t("Explosive damage")
        }
        for damageType in DamagePattern.DAMAGE_TYPES:
            bitmap = BitmapLoader.getStaticBitmap("%s_small" % damageType, contentPanel, "gui")
            bitmap.SetToolTip(wx.ToolTip(toolTipText[damageType]))
            ammoSizer.Add(bitmap, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
            label = wx.StaticText(contentPanel, wx.ID_ANY, "0")
            label.SetToolTip(wx.ToolTip(toolTipText[damageType]))
            ammoSizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 1)
            setattr(self, "bitmapDamage%s" % damageType.capitalize(), bitmap)
            setattr(self, "labelDamage%s" % damageType.capitalize(), label)

    def OnWeaponChange(self, event):
        self.settings.set('weapon', list(WEAPONS)[event.GetSelection()])
        self.refreshActiveFit()

    def refreshActiveFit(self):
        fit = Fit.getInstance().getFit(self.activeFit) if self.activeFit is not None else None
        self.refreshPanel(fit)

    def getCharges(self, weapon):
        # returns (charge, typeID of the module using it) pairs
        if weapon not in self._chargeCache:
            charges = []
            for typeID in WEAPONS[weapon][1]:
                item = Market.getInstance().getItem(typeID)
                if item is None:
                    continue
                charges.extend((charge, typeID) for charge in Ammo.getModuleFlatAmmo(Module(item)))
            self._chargeCache[weapon] = charges
        return self._chargeCache[weapon]

    @staticmethod
    def getChargeTier(charge):
        sMkt = Market.getInstance()
        metaGroupID = sMkt.getMetaGroupIdByItem(charge)
        # Meta group 2 is Tech II
        if metaGroupID == 2:
            return 't2'
        if metaGroupID in sMkt.META_MAP['faction']:
            # imported here to avoid circular imports with the graph package
            from graphs.data.fitApplicationProfile.calc.charges import CAPITAL_NAVY_PREFIXES, NAVY_PREFIXES
            # there is no empire navy XL ammo, so pirate faction is the navy tier for capitals
            navyPrefixes = CAPITAL_NAVY_PREFIXES if charge.name.endswith(' XL') else NAVY_PREFIXES
            if charge.name.startswith(navyPrefixes):
                return 'faction'
            return 'officer'
        return 't1'

    @staticmethod
    def getChargeName(charge):
        # size does not matter for the damage ratios, so we don't show it
        return CHARGE_SIZE_SUFFIX.sub('', charge.name)

    def showWorstAmmo(self, charge, damage):
        bitmap = BitmapLoader.getBitmap(charge.iconID, "icons") if charge is not None and charge.iconID else None
        self.bitmapWorstAmmo.SetBitmap(bitmap if bitmap is not None else wx.NullBitmap)
        self.bitmapWorstAmmo.Show(bitmap is not None)
        damage = damage or [0] * 4
        totalDamage = sum(damage)
        for damageType, amount in zip(DamagePattern.DAMAGE_TYPES, damage):
            bitmap = getattr(self, "bitmapDamage%s" % damageType.capitalize())
            label = getattr(self, "labelDamage%s" % damageType.capitalize())
            label.SetLabel("%d%%" % round(amount / totalDamage * 100) if totalDamage else "0%")
            bitmap.Show(amount > 0)
            label.Show(amount > 0)

    def refreshPanel(self, fit):
        # If we did anything interesting, we'd update our labels to reflect the new fit's stats here
        self.activeFit = fit.ID if fit is not None else None

        weapon = list(WEAPONS)[self.weaponChoice.GetSelection()]
        tiers = {tier for tier in TIERS if self.settings.get(tier)}

        # collect the damage of every charge the selected weapon can use
        allChargeDamages = []
        for charge, typeID in self.getCharges(weapon):
            damage = [charge.getAttribute('%sDamage' % damageType, default=0)
                      for damageType in DamagePattern.DAMAGE_TYPES]
            if sum(damage) <= 0:
                continue
            allChargeDamages.append((charge, damage, typeID))
        chargeDamages = [(charge, damage, typeID) for charge, damage, typeID in allChargeDamages
                         if self.getChargeTier(charge) in tiers]

        if fit is None or not chargeDamages:
            for tankType in ("shield", "armor", "hull", "total"):
                label = getattr(self, "labelEhp%s" % tankType.capitalize())
                label.SetLabel("0")
                label.UnsetToolTip()
            self.labelWorstAmmo.SetLabel(_t("None") if fit is not None else "")
            self.labelWorstAmmo.UnsetToolTip()
            self.showWorstAmmo(None, None)
            self.layoutIfNeeded()
            return

        # ammo with lower damage needs more shots, so to pick the worst case ammo we scale the EHP of each ammo by
        # its damage relative to the strongest ammo. This way an ammo which hits a resist hole but deals less
        # damage overall is not automatically the worst case. If only the damage type split is considered, we skip
        # the scaling. The scaling is only used to pick the ammo, the shown EHP is always the EHP against the damage
        # type split of the worst case ammo. Charges of different modules (e.g. missiles and bombs) are only
        # compared to the strongest charge of their own module
        includeDamage = self.settings.get('includeDamage')
        strongest = {}
        for charge, damage, typeID in allChargeDamages:
            if typeID not in strongest or sum(damage) > sum(strongest[typeID][1]):
                strongest[typeID] = (charge, damage)
        results = []
        for charge, damage, typeID in chargeDamages:
            pattern = DamagePattern(*damage)
            ehp = pattern.calculateEhp(fit.ship)
            ehp["total"] = sum(ehp.values())
            relativeDamage = sum(damage) / sum(strongest[typeID][1])
            adjustedTotal = ehp["total"] / relativeDamage if includeDamage else ehp["total"]
            results.append((charge, damage, ehp, relativeDamage, adjustedTotal))
        # ammo with the same damage type split ties when only the split is considered, prefer the stronger one
        results.sort(key=lambda r: (round(r[4], 3), -r[3], r[0].name))

        worstCharge, worstDamage, worstEhp = results[0][:3]
        if weapon in DAMAGE_TYPE_WEAPONS:
            worstDamageType = DamagePattern.DAMAGE_TYPES[worstDamage.index(max(worstDamage))]
            worstName = _t(DAMAGE_TYPE_WEAPONS[weapon][worstDamageType])
            worstIconCharge = None
        else:
            worstName = self.getChargeName(worstCharge)
            worstIconCharge = worstCharge

        for tankType, tooltip in (("shield", _t("Shield: ")), ("armor", _t("Armor: ")), ("hull", _t("Hull: ")),
                                  ("total", _t("Total: "))):
            label = getattr(self, "labelEhp%s" % tankType.capitalize())
            label.SetLabel(formatAmount(worstEhp[tankType], 3, 0, 9))
            label.SetToolTip(wx.ToolTip(tooltip + "%d" % worstEhp[tankType]))

        self.labelWorstAmmo.SetLabel(worstName)
        if includeDamage:
            lines = [_t("EHP vs. each ammo, worst case first (damage relative to the strongest ammo):")]
            for charge, damage, ehp, relativeDamage, adjustedTotal in results:
                lines.append("%s: %s (%d%%)" % (
                    self.getChargeName(charge), formatAmount(ehp["total"], 3, 0, 9), round(relativeDamage * 100)))
        else:
            lines = [_t("EHP vs. the damage type split of each ammo:")]
            for charge, damage, ehp, relativeDamage, adjustedTotal in results:
                lines.append("%s: %s" % (self.getChargeName(charge), formatAmount(ehp["total"], 3, 0, 9)))
        self.labelWorstAmmo.SetToolTip(wx.ToolTip("\n".join(lines)))
        self.showWorstAmmo(worstIconCharge, worstDamage)

        self.layoutIfNeeded()


WorstCaseEhpViewFull.register()
