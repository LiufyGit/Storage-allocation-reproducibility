# -*- coding: utf-8 -*-
"""
Created on Mon Oct  6 20:38:11 2025

@author: AdminLiufy
"""
import time
from pathlib import Path
import gurobipy as gp
from gurobipy import GRB
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
##################----鑺傜偣1------###########################
node_one_data = pd.read_csv(ROOT / "723035.csv", index_col=0)#璇诲彇鑺傜偣1鏁版嵁
node_one_pvpower = node_one_data.iloc[:,1] #鍏変紡鍑哄姏鏁版嵁
node_one_load = node_one_data.iloc[:,0] #璐熻嵎鏁版嵁
N_variable = 8760
cost_pv = 691*1000     #鍏変紡浠锋牸 $/MW
maintenance_cost_pv = 0.01   #鍏変紡杩愮淮鎴愭湰
life_pv = 30
cost_battery = 115*1000  #鐢垫睜浠锋牸 $/MWh
maintenance_cost_battery = 0.0002  #鍌ㄨ兘杩愮淮鎴愭湰
discount_rate = 0.08
life_battery = 15
capital_recovery_factor_pv = (discount_rate * (1 + discount_rate) ** (life_pv)) / ((1 + discount_rate) ** (life_pv) - 1)
capital_recovery_factor_battery = (discount_rate * (1 + discount_rate) ** (life_battery)) / ((1 + discount_rate) ** (life_battery) - 1)
self_discharge_rate = 0.01/100
charging_discharging_efficiency = 0.95
pv_rated_power_one = sum(node_one_load)/sum(node_one_pvpower)  #鍘熸湁鍏変紡鏈虹粍瀹归噺 MW 

##################----鑺傜偣2------###########################
node_two_data = pd.read_csv(ROOT / "747910.csv", index_col=0)#璇诲彇鑺傜偣2鏁版嵁
node_two_pvpower = node_two_data.iloc[:,1] #鍏変紡鍑哄姏鏁版嵁
node_two_load = node_two_data.iloc[:,0] #璐熻嵎鏁版嵁
pv_rated_power_two = sum(node_two_load)/sum(node_two_pvpower)  #鍘熸湁鍏変紡鏈虹粍瀹归噺 MW 


##################----鑺傜偣3------###########################
node_three_data = pd.read_csv(ROOT / "747915.csv", index_col=0)#璇诲彇鑺傜偣3鏁版嵁
node_three_pvpower = node_three_data.iloc[:,1] #鍏変紡鍑哄姏鏁版嵁
node_three_load = node_three_data.iloc[:,0] #璐熻嵎鏁版嵁
pv_rated_power_three = sum(node_three_load)/sum(node_three_pvpower)  #鍘熸湁鍏変紡鏈虹粍瀹归噺 MW 

# 鍒涘缓妯″瀷
overbuilt_curtailmen4=gp.Model("overbuilt_curtailmen4")
# 鍙橀噺澹版槑
Pcharge1  = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pcharge ")
Pcharge2  = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pcharge ")
Pcharge3  = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pcharge ")
Pdischarge  = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pdischarge")
Bcharge = overbuilt_curtailmen4.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bcharge')
Bdischarge = overbuilt_curtailmen4.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bdischarge')
Sbattery = overbuilt_curtailmen4.addVar(vtype=GRB.CONTINUOUS, name='Sbattery')
Sstorage = overbuilt_curtailmen4.addVars(N_variable, 1, vtype=GRB.CONTINUOUS, name='Sstorage')

pv_multiple1 = overbuilt_curtailmen4.addVar(vtype=GRB.CONTINUOUS, name='multiplier')
Pcurt1 = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Pcurt')
Ppvtoload1 = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Ppvtoload')

pv_multiple2 = overbuilt_curtailmen4.addVar(vtype=GRB.CONTINUOUS, name='multiplier')
Pcurt2 = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Pcurt')
Ppvtoload2 = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Ppvtoload')

pv_multiple3 = overbuilt_curtailmen4.addVar(vtype=GRB.CONTINUOUS, name='multiplier')
Pcurt3 = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Pcurt')
Ppvtoload3 = overbuilt_curtailmen4.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Ppvtoload')

# 璁剧疆鐩爣鍑芥暟
overbuilt_curtailmen4.setObjective(capital_recovery_factor_pv * pv_rated_power_one * cost_pv * pv_multiple1 + \
                                   maintenance_cost_pv * pv_rated_power_one * cost_pv * pv_multiple1 + \
                                   # capital_recovery_factor_pv * pv_rated_power_two * cost_pv * pv_multiple2 + \
                                   # maintenance_cost_pv * pv_rated_power_two * cost_pv * pv_multiple2 + \
                                   capital_recovery_factor_pv * pv_rated_power_three * cost_pv * pv_multiple3 + \
                                   maintenance_cost_pv * pv_rated_power_three * cost_pv * pv_multiple3 + \
                                   capital_recovery_factor_battery * cost_battery * Sbattery + \
                                   maintenance_cost_battery * cost_battery * sum(Pcharge1[t,0] + Pcharge3[t,0] for t in range(N_variable)), \
                                   GRB.MINIMIZE)#1-2琛屼负鑺傜偣1鍏変紡绛夊勾鍊兼垚鏈紝3-4琛屼负鑺傜偣2鍏変紡绛夊勾鍊兼垚鏈紝5-6琛屼负鑺傜偣3鍏変紡绛夊勾鍊兼垚鏈紝
   
# 娣诲姞绾︽潫
overbuilt_curtailmen4.addConstrs((Bcharge[t,0] + Bdischarge[t,0] <= 1 for t in range(N_variable)), name= 'charge_and_discharge_binary')
overbuilt_curtailmen4.addConstrs((Pcharge1[t,0] + Pcharge3[t,0] <= Bcharge[t,0] * Sbattery /4 for t in range(N_variable)), name='chargecons')
overbuilt_curtailmen4.addConstrs((Pdischarge[t,0] <= Bdischarge[t,0] * Sbattery /4 for t in range(N_variable)), name='dischargecons')
overbuilt_curtailmen4.addConstrs((Sstorage[t,0] <= Sbattery for t in range(N_variable)), name='battery_storage_cons')
overbuilt_curtailmen4.addConstr((Sstorage[0,0] == 0.8 * Sbattery), name='initial_battery_storage_cons')
overbuilt_curtailmen4.addConstrs((Sstorage[t+1,0] == (1 - self_discharge_rate) * Sstorage[t,0] + (Pcharge1[t,0] +  Pcharge3[t,0]) * charging_discharging_efficiency - Pdischarge[t,0]/charging_discharging_efficiency for t in range(N_variable-1)), name='storage_balance_cons')
overbuilt_curtailmen4.addConstr((Sstorage[0,0] == (1 - self_discharge_rate) * Sstorage[8760-1,0] + (Pcharge1[8760-1,0]+Pcharge3[8760-1,0]) * charging_discharging_efficiency - Pdischarge[8760-1,0]/charging_discharging_efficiency), name='storage_balance_cons')


overbuilt_curtailmen4.addConstrs((Ppvtoload1[t,0]  + Ppvtoload3[t,0] + Pdischarge[t,0] == node_one_load[t]  + node_three_load[t] for t in range(N_variable)), name='load_demand_cons')
overbuilt_curtailmen4.addConstrs((Ppvtoload1[t,0] + Pcharge1[t,0] + Pcurt1[t,0] == pv_multiple1 *pv_rated_power_one* node_one_pvpower[t] for t in range(N_variable)), name='pv_power_cons')
# overbuilt_curtailmen4.addConstrs((Ppvtoload2[t,0] + Pcharge2[t,0] + Pcurt2[t,0] == pv_multiple2 *pv_rated_power_two* node_two_pvpower[t] for t in range(N_variable)), name='pv_power_cons')
overbuilt_curtailmen4.addConstrs((Ppvtoload3[t,0] + Pcharge3[t,0] + Pcurt3[t,0] == pv_multiple3 *pv_rated_power_three* node_three_pvpower[t] for t in range(N_variable)), name='pv_power_cons')
# Optimize model
overbuilt_curtailmen4.optimize()
# obj4 = overbuilt_curtailmen4.objVal
# one_multiplier_cost1 = capital_recovery_factor_pv * pv_rated_power_one * cost_pv  + maintenance_cost_pv * pv_rated_power_one * cost_pv
# one_multiplier_cost2 = capital_recovery_factor_pv * pv_rated_power_two * cost_pv  + maintenance_cost_pv * pv_rated_power_two * cost_pv
# one_multiplier_cost3 = capital_recovery_factor_pv * pv_rated_power_three * cost_pv  + maintenance_cost_pv * pv_rated_power_three * cost_pv




total_Pcharge_cost = sum(Pcharge1[t, 0].X  + Pcharge3[t, 0].X for t in range(N_variable))

energy_cost_node_three = (capital_recovery_factor_battery * cost_battery * Sbattery.X + 
                           maintenance_cost_battery * cost_battery * total_Pcharge_cost)

print(f"pair_storage_capacity_mwh: {Sbattery.X}")
print(f"pair_storage_cost_usd: {energy_cost_node_three}")
print(f"pair_objective_usd_per_year: {overbuilt_curtailmen4.objVal}")






