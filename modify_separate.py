# -*- coding: utf-8 -*-
"""
Created on Mon Oct  6 00:17:04 2025
鍗曠嫭浼樺寲瀹屽杽 淇敼鏀惧ぇ鍊?
@author: AdminLiufy
"""
# -*- coding: utf-8 -*-

import time
from pathlib import Path
import gurobipy as gp
from gurobipy import GRB
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent

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

# 鍒涘缓妯″瀷
overbuilt_curtailmen1=gp.Model("overbuilt_curtailmen1")
# 鍙橀噺澹版槑
Pcharge  = overbuilt_curtailmen1.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pcharge ")
Pdischarge  = overbuilt_curtailmen1.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pdischarge")
Pcurt = overbuilt_curtailmen1.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Pcurt')
Ppvtoload = overbuilt_curtailmen1.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Ppvtoload')
Sbattery = overbuilt_curtailmen1.addVar(vtype=GRB.CONTINUOUS, name='Sbattery')
pv_multiple = overbuilt_curtailmen1.addVar(vtype=GRB.CONTINUOUS, name='multiplier')
Sstorage = overbuilt_curtailmen1.addVars(N_variable, 1, vtype=GRB.CONTINUOUS, name='Sstorage')
Bcharge = overbuilt_curtailmen1.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bcharge')
Bdischarge = overbuilt_curtailmen1.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bdischarge')

# 璁剧疆鐩爣鍑芥暟
overbuilt_curtailmen1.setObjective(capital_recovery_factor_pv * pv_rated_power_one * cost_pv * pv_multiple + \
                                   maintenance_cost_pv * pv_rated_power_one * cost_pv * pv_multiple + \
                                   capital_recovery_factor_battery * cost_battery * Sbattery + \
                                   maintenance_cost_battery * cost_battery * sum(Pcharge[t,0] for t in range(N_variable)), \
                                   GRB.MINIMIZE)
   
# 娣诲姞绾︽潫
overbuilt_curtailmen1.addConstrs((Bcharge[t,0] + Bdischarge[t,0] <= 1 for t in range(N_variable)), name= 'charge_and_discharge_binary')
overbuilt_curtailmen1.addConstrs((Pcharge[t,0] <= Bcharge[t,0] * Sbattery /4 for t in range(N_variable)), name='chargecons')
overbuilt_curtailmen1.addConstrs((Pdischarge[t,0] <= Bdischarge[t,0] * Sbattery /4 for t in range(N_variable)), name='dischargecons')
overbuilt_curtailmen1.addConstrs((Sstorage[t,0] <= Sbattery for t in range(N_variable)), name='battery_storage_cons')
overbuilt_curtailmen1.addConstr((Sstorage[0,0] == 0.8 * Sbattery), name='initial_battery_storage_cons')
overbuilt_curtailmen1.addConstrs((Ppvtoload[t,0] + Pdischarge[t,0] == node_one_load[t] for t in range(N_variable)), name='load_demand_cons')
overbuilt_curtailmen1.addConstrs((Ppvtoload[t,0] + Pcharge[t,0] + Pcurt[t,0] == pv_multiple *pv_rated_power_one *node_one_pvpower[t] for t in range(N_variable)), name='pv_power_cons')
overbuilt_curtailmen1.addConstrs((Sstorage[t+1,0] == (1 - self_discharge_rate) * Sstorage[t,0] + Pcharge[t,0] * charging_discharging_efficiency - Pdischarge[t,0]/charging_discharging_efficiency for t in range(N_variable-1)), name='storage_balance_cons')
overbuilt_curtailmen1.addConstr((Sstorage[0,0] == (1 - self_discharge_rate) * Sstorage[8760-1,0] + Pcharge[8760-1,0] * charging_discharging_efficiency - Pdischarge[8760-1,0]/charging_discharging_efficiency), name='storage_balance_cons')

# Optimize model
overbuilt_curtailmen1.optimize()
obj1 = overbuilt_curtailmen1.objVal
one_multiplier_cost1 = capital_recovery_factor_pv * pv_rated_power_one * cost_pv  + maintenance_cost_pv * pv_rated_power_one * cost_pv
multiple_cost = capital_recovery_factor_pv * pv_rated_power_one * cost_pv * pv_multiple.X + maintenance_cost_pv * pv_rated_power_one * cost_pv * pv_multiple.X
battery_capacity =  Sbattery.X

print(pv_multiple.X)
print(battery_capacity)

LCOH_firm = obj1/(sum(node_one_load))
LCOH_unconstrained = one_multiplier_cost1/(sum(node_one_pvpower)*pv_rated_power_one)
premium = LCOH_firm/LCOH_unconstrained
print(premium)
energy_cost_node_one = (capital_recovery_factor_battery * cost_battery * Sbattery.X + 
                         maintenance_cost_battery * cost_battery * sum(Pcharge[t, 0].X for t in range(N_variable)))

print(f"鑺傜偣1鐨勫厜浼忓偍鑳芥垚鏈? {energy_cost_node_one}")
print(obj1)
##################----鑺傜偣2------###########################
node_two_data = pd.read_csv(ROOT / "747910.csv", index_col=0)#璇诲彇鑺傜偣2鏁版嵁
node_two_pvpower = node_two_data.iloc[:,1] #鍏変紡鍑哄姏鏁版嵁
node_two_load = node_two_data.iloc[:,0] #璐熻嵎鏁版嵁
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
pv_rated_power_two = sum(node_two_load)/sum(node_two_pvpower)  #鍘熸湁鍏変紡鏈虹粍瀹归噺 MW 

# 鍒涘缓妯″瀷
overbuilt_curtailmen2=gp.Model("overbuilt_curtailmen2")
# 鍙橀噺澹版槑
Pcharge  = overbuilt_curtailmen2.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pcharge ")
Pdischarge  = overbuilt_curtailmen2.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pdischarge")
Pcurt = overbuilt_curtailmen2.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Pcurt')
Ppvtoload = overbuilt_curtailmen2.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Ppvtoload')
Sbattery = overbuilt_curtailmen2.addVar(vtype=GRB.CONTINUOUS, name='Sbattery')
pv_multiple = overbuilt_curtailmen2.addVar(vtype=GRB.CONTINUOUS, name='multiplier')
Sstorage = overbuilt_curtailmen2.addVars(N_variable, 1, vtype=GRB.CONTINUOUS, name='Sstorage')
Bcharge = overbuilt_curtailmen2.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bcharge')
Bdischarge = overbuilt_curtailmen2.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bdischarge')

# 璁剧疆鐩爣鍑芥暟
overbuilt_curtailmen2.setObjective(capital_recovery_factor_pv * pv_rated_power_two * cost_pv * pv_multiple + \
                                   maintenance_cost_pv * pv_rated_power_two * cost_pv * pv_multiple + \
                                   capital_recovery_factor_battery * cost_battery * Sbattery + \
                                   maintenance_cost_battery * cost_battery * sum(Pcharge[t,0] for t in range(N_variable)), \
                                   GRB.MINIMIZE)
   
# 娣诲姞绾︽潫
overbuilt_curtailmen2.addConstrs((Bcharge[t,0] + Bdischarge[t,0] <= 1 for t in range(N_variable)), name= 'charge_and_discharge_binary')
overbuilt_curtailmen2.addConstrs((Pcharge[t,0] <= Bcharge[t,0] * Sbattery /4 for t in range(N_variable)), name='chargecons')
overbuilt_curtailmen2.addConstrs((Pdischarge[t,0] <= Bdischarge[t,0] * Sbattery /4 for t in range(N_variable)), name='dischargecons')
overbuilt_curtailmen2.addConstrs((Sstorage[t,0] <= Sbattery for t in range(N_variable)), name='battery_storage_cons')
overbuilt_curtailmen2.addConstr((Sstorage[0,0] == 0.8 * Sbattery), name='initial_battery_storage_cons')
overbuilt_curtailmen2.addConstrs((Ppvtoload[t,0] + Pdischarge[t,0] == node_two_load[t] for t in range(N_variable)), name='load_demand_cons')
overbuilt_curtailmen2.addConstrs((Ppvtoload[t,0] + Pcharge[t,0] + Pcurt[t,0] == pv_multiple*pv_rated_power_two * node_two_pvpower[t] for t in range(N_variable)), name='pv_power_cons')
overbuilt_curtailmen2.addConstrs((Sstorage[t+1,0] == (1 - self_discharge_rate) * Sstorage[t,0] + Pcharge[t,0] * charging_discharging_efficiency - Pdischarge[t,0]/charging_discharging_efficiency for t in range(N_variable-1)), name='storage_balance_cons')
overbuilt_curtailmen2.addConstr((Sstorage[0,0] == (1 - self_discharge_rate) * Sstorage[8760-1,0] + Pcharge[8760-1,0] * charging_discharging_efficiency - Pdischarge[8760-1,0]/charging_discharging_efficiency), name='storage_balance_cons')

# Optimize model
overbuilt_curtailmen2.optimize()
obj2 = overbuilt_curtailmen2.objVal
one_multiplier_cost2 = capital_recovery_factor_pv * pv_rated_power_two * cost_pv  + maintenance_cost_pv * pv_rated_power_two * cost_pv
multiple_cost = capital_recovery_factor_pv * pv_rated_power_two * cost_pv * pv_multiple.X + maintenance_cost_pv * pv_rated_power_two * cost_pv * pv_multiple.X
battery_capacity =  Sbattery.X

print(pv_multiple.X)
print(battery_capacity)

LCOH_firm = obj2/(sum(node_two_load))
LCOH_unconstrained = one_multiplier_cost2/(sum(node_two_pvpower)*pv_rated_power_two)
premium = LCOH_firm/LCOH_unconstrained
print(premium)
energy_cost_node_two = (capital_recovery_factor_battery * cost_battery * Sbattery.X + 
                         maintenance_cost_battery * cost_battery * sum(Pcharge[t, 0].X for t in range(N_variable)))

print(f"鑺傜偣2鐨勫厜浼忓偍鑳芥垚鏈? {energy_cost_node_two}")
print(obj2)
##################----鑺傜偣3------###########################
node_three_data = pd.read_csv(ROOT / "747915.csv", index_col=0)#璇诲彇鑺傜偣3鏁版嵁
node_three_pvpower = node_three_data.iloc[:,1] #鍏変紡鍑哄姏鏁版嵁
node_three_load = node_three_data.iloc[:,0] #璐熻嵎鏁版嵁
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
pv_rated_power_three = sum(node_three_load)/sum(node_three_pvpower)  #鍘熸湁鍏変紡鏈虹粍瀹归噺 MW 

# 鍒涘缓妯″瀷
overbuilt_curtailmen3=gp.Model("overbuilt_curtailmen3")
# 鍙橀噺澹版槑
Pcharge  = overbuilt_curtailmen3.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pcharge ")
Pdischarge  = overbuilt_curtailmen3.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name="Pdischarge")
Pcurt = overbuilt_curtailmen3.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Pcurt')
Ppvtoload = overbuilt_curtailmen3.addVars(N_variable,1, vtype=GRB.CONTINUOUS, name='Ppvtoload')
Sbattery = overbuilt_curtailmen3.addVar(vtype=GRB.CONTINUOUS, name='Sbattery')
pv_multiple = overbuilt_curtailmen3.addVar(vtype=GRB.CONTINUOUS, name='multiplier')
Sstorage = overbuilt_curtailmen3.addVars(N_variable, 1, vtype=GRB.CONTINUOUS, name='Sstorage')
Bcharge = overbuilt_curtailmen3.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bcharge')
Bdischarge = overbuilt_curtailmen3.addVars(N_variable, 1, vtype=GRB.BINARY, name='Bdischarge')

# 璁剧疆鐩爣鍑芥暟
overbuilt_curtailmen3.setObjective(capital_recovery_factor_pv * pv_rated_power_three * cost_pv * pv_multiple + \
                                   maintenance_cost_pv * pv_rated_power_three * cost_pv * pv_multiple + \
                                   capital_recovery_factor_battery * cost_battery * Sbattery + \
                                   maintenance_cost_battery * cost_battery * sum(Pcharge[t,0] for t in range(N_variable)), \
                                   GRB.MINIMIZE)
   
# 娣诲姞绾︽潫
overbuilt_curtailmen3.addConstrs((Bcharge[t,0] + Bdischarge[t,0] <= 1 for t in range(N_variable)), name= 'charge_and_discharge_binary')
overbuilt_curtailmen3.addConstrs((Pcharge[t,0] <= Bcharge[t,0] * Sbattery /4 for t in range(N_variable)), name='chargecons')
overbuilt_curtailmen3.addConstrs((Pdischarge[t,0] <= Bdischarge[t,0] * Sbattery /4 for t in range(N_variable)), name='dischargecons')
overbuilt_curtailmen3.addConstrs((Sstorage[t,0] <= Sbattery for t in range(N_variable)), name='battery_storage_cons')
overbuilt_curtailmen3.addConstr((Sstorage[0,0] == 0.8 * Sbattery), name='initial_battery_storage_cons')
overbuilt_curtailmen3.addConstrs((Ppvtoload[t,0] + Pdischarge[t,0] == node_three_load[t] for t in range(N_variable)), name='load_demand_cons')
overbuilt_curtailmen3.addConstrs((Ppvtoload[t,0] + Pcharge[t,0] + Pcurt[t,0] == pv_multiple* pv_rated_power_three * node_three_pvpower[t] for t in range(N_variable)), name='pv_power_cons')
overbuilt_curtailmen3.addConstrs((Sstorage[t+1,0] == (1 - self_discharge_rate) * Sstorage[t,0] + Pcharge[t,0] * charging_discharging_efficiency - Pdischarge[t,0]/charging_discharging_efficiency for t in range(N_variable-1)), name='storage_balance_cons')
overbuilt_curtailmen3.addConstr((Sstorage[0,0] == (1 - self_discharge_rate) * Sstorage[8760-1,0] + Pcharge[8760-1,0] * charging_discharging_efficiency - Pdischarge[8760-1,0]/charging_discharging_efficiency), name='storage_balance_cons')

# Optimize model
overbuilt_curtailmen3.optimize()
obj3 = overbuilt_curtailmen3.objVal
one_multiplier_cost3 = capital_recovery_factor_pv * pv_rated_power_three * cost_pv  + maintenance_cost_pv * pv_rated_power_three * cost_pv
multiple_cost = capital_recovery_factor_pv * pv_rated_power_three * cost_pv * pv_multiple.X + maintenance_cost_pv * pv_rated_power_three * cost_pv * pv_multiple.X
battery_capacity =  Sbattery.X

print(pv_multiple.X)
print(battery_capacity)

LCOH_firm = obj3/(sum(node_three_load))
LCOH_unconstrained = one_multiplier_cost3/(sum(node_three_pvpower)*pv_rated_power_three)
premium = LCOH_firm/LCOH_unconstrained
print(premium)
energy_cost_node_three = (capital_recovery_factor_battery * cost_battery * Sbattery.X + 
                           maintenance_cost_battery * cost_battery * sum(Pcharge[t, 0].X for t in range(N_variable)))

print(f"鑺傜偣3鐨勫厜浼忓偍鑳芥垚鏈? {energy_cost_node_three}")
print(obj3)
##############鏁翠釜绯荤粺鐨勬孩浠?
LCOH_firm = (obj1+obj2+obj3)/sum(node_one_load+node_two_load+node_three_load)
LCOH_unconstrained = (one_multiplier_cost1+one_multiplier_cost2+one_multiplier_cost3)/(pv_rated_power_one*sum(node_one_pvpower)+pv_rated_power_two*sum(node_two_pvpower)+pv_rated_power_three*sum(node_three_pvpower))
premium = LCOH_firm/LCOH_unconstrained
print(premium)


