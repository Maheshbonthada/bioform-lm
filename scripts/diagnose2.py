import sys, json, statistics as st
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data import synthetic_generator as sg
gen = sg.SyntheticDataGenerator(num_samples=1, seed=0); sim = gen.simulator
def score(p,f): return sim.predict(p,f).stability_score

rows=[]
for _ in range(60):
    pr = gen._sample_protein()
    cands=[gen._sample_formulation() for _ in range(2000)]
    ss=np.array([score(pr,c) for c in cands]); b=cands[int(np.argmax(ss))]
    rows.append({"pi":pr.pi,"mw":pr.mw_kda,"tm":pr.tm_baseline_c,"ph":b.ph,
                 "ion":b.ionic_strength_mm,"osm":b.osmolarity_mosm_kg,
                 "temp":b.temperature_c,"best":float(ss.max())})
box={"ph":(3.5,9.0),"ion":(10,500),"osm":(150,400),"temp":(4,37)}
rep={}
for k,(lo,hi) in box.items():
    v=[r[k] for r in rows]
    rep[k]={"opt_min":min(v),"opt_max":max(v),"opt_sd":st.pstdev(v),
            "frac_of_box_spanned":(max(v)-min(v))/(hi-lo)}
ph=np.array([r["ph"] for r in rows]); pi=np.array([r["pi"] for r in rows])
rep["ph_vs_pi_corr"]=float(np.corrcoef(ph,pi)[0,1])
rep["ph_corner_frac"]=float(np.mean((ph<3.8)|(ph>8.7)))
print(json.dumps(rep,indent=2))
d=json.loads(Path("results/simulator_diagnosis_v1.json").read_text())
d["H2c_optimum_geometry"]=rep
Path("results/simulator_diagnosis_v1.json").write_text(json.dumps(d,indent=2))
