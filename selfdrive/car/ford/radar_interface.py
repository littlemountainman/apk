#!/usr/bin/env python
import os
import numpy as np
from selfdrive.can.parser import CANParser
from cereal import car
from common.realtime import sec_since_boot
import zmq
from selfdrive.services import service_list
import selfdrive.messaging as messaging


RADAR_MSGS = range(0x500, 0x540)

def _create_radar_can_parser():
  dbc_f = 'ford_fusion_2018_adas.dbc'
  msg_n = len(RADAR_MSGS)
  signals = list(zip(['X_Rel'] * msg_n + ['Angle'] * msg_n + ['V_Rel'] * msg_n,
                     RADAR_MSGS * 3,
                     [0] * msg_n + [0] * msg_n + [0] * msg_n))
  checks = list(zip(RADAR_MSGS, [20]*msg_n))

  return CANParser(os.path.splitext(dbc_f)[0], signals, checks, 1)

class RadarInterface(object):
  def __init__(self, CP):
    # radar
    self.pts = {}
    self.validCnt = {key: 0 for key in RADAR_MSGS}
    self.track_id = 0

    self.delay = 0.0  # Delay of radar

    # Nidec
    self.rcp = _create_radar_can_parser()

    context = zmq.Context()
    self.logcan = messaging.sub_sock(context, service_list['can'].port)

  def update(self):
    canMonoTimes = []

    updated_messages = set()
    while 1:
      tm = int(sec_since_boot() * 1e9)
      _, vls = self.rcp.update(tm, True)
      updated_messages.update(vls)

      # TODO: do not hardcode last msg
      if 0x53f in updated_messages:
        break

    ret = car.RadarData.new_message()
    errors = []
    if not self.rcp.can_valid:
      errors.append("commIssue")
    ret.errors = errors
    ret.canMonoTimes = canMonoTimes

    for ii in updated_messages:
      cpt = self.rcp.vl[ii]

      if cpt['X_Rel'] > 0.00001:
        self.validCnt[ii] = 0    # reset counter

      if cpt['X_Rel'] > 0.00001:
        self.validCnt[ii] += 1
      else:
        self.validCnt[ii] = max(self.validCnt[ii] -1, 0)
      #print ii, self.validCnt[ii], cpt['VALID'], cpt['X_Rel'], cpt['Angle']

      # radar point only valid if there have been enough valid measurements
      if self.validCnt[ii] > 0:
        if ii not in self.pts:
          self.pts[ii] = car.RadarData.RadarPoint.new_message()
          self.pts[ii].trackId = self.track_id
          self.track_id += 1
        self.pts[ii].dRel = cpt['X_Rel']  # from front of car
        self.pts[ii].yRel = cpt['X_Rel'] * cpt['Angle'] * np.pi / 180.  # in car frame's y axis, left is positive
        self.pts[ii].vRel = cpt['V_Rel']
        self.pts[ii].aRel = float('nan')
        self.pts[ii].yvRel = float('nan')
        self.pts[ii].measured = True
      else:
        if ii in self.pts:
          del self.pts[ii]

    ret.points = self.pts.values()
    return ret

if __name__ == "__main__":
  RI = RadarInterface(None)
  while 1:
    ret = RI.update()
    print(chr(27) + "[2J")
    print(ret)
