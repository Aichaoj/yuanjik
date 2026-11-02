# -*- coding: utf-8 -*-
p = r'shuzi\web\energy.js'
s = open(p, encoding='utf-8').read()
old = """  window.YJEnergy = {
    init: initEnergy,"""
assert s.count(old) == 1
new = """  window.YJEnergy = {
    init: initEnergy,
    togglePart: togglePart,
    inject: inject,
    turn: turn,
    picked: function () { return picked.slice(); },"""
open(p, 'w', encoding='utf-8', newline='\n').write(s.replace(old, new))
print('exports ok')
