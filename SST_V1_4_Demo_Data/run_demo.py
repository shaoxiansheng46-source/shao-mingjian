"""Standard-library demo pipeline. Synthetic data; not an engineering solver.
Run: python3 run_demo.py --self-test
     python3 run_demo.py --input sample_input_feasible.json
"""
import argparse, csv, hashlib, itertools, json, math
from collections import Counter
from pathlib import Path

BASE=Path(__file__).resolve().parent
MU0=4*math.pi*1e-7
EPS0=8.8541878128e-12

def load(name):
    return json.loads((BASE/name).read_text(encoding='utf-8'))

def idx(name):
    return {x['id']:x for x in load(name)}

def validate_database():
    mats=idx('core_material_library.json');cores=idx('core_geometry_library.json')
    wires=idx('litz_library.json');ins=idx('insulation_library.json')
    layouts=idx('winding_layout_templates.json');models=idx('model_registry.json')
    rules=idx('design_rule_library.json')
    for name in ['core_material_library.json','core_geometry_library.json','litz_library.json',
                 'insulation_library.json','winding_layout_templates.json','model_registry.json','design_rule_library.json']:
        items=load(name)
        assert len({x['id'] for x in items})==len(items),name
        assert all(x['data_status']=='synthetic' and not x['engineering_approved'] for x in items)
    for c in cores.values():
        assert c['material_id'] in mats
        assert math.isclose(c['Aw_mm2'],c['window_height_mm']*c['window_width_mm'])
        assert math.isclose(c['Ae_mm2'],c['leg_width_mm']*c['leg_depth_mm'])
        assert c['Ve_mm3'] < math.prod(c['core_outer_mm'])
        assert all(x in layouts for x in c['allowed_layout_ids'])
        assert c['gap_model_id'] in models
    for w in wires.values():
        area=w['strand_count']*math.pi*w['strand_bare_diameter_mm']**2/4
        assert math.isclose(w['copper_area_mm2'],area)
        assert area < math.pi*w['outer_diameter_mm']**2/4
        assert w['ac_resistance_model_id'] in models
    for l in layouts.values():
        assert l['layer_insulation_id'] in ins and l['main_insulation_id'] in ins
        for k in ['mlt_model_id','thermal_model_id','leakage_model_id','capacitance_model_id']:
            assert l[k] is None or l[k] in models
    return mats,cores,wires,ins,layouts,models,rules

def interpolate(points,x,key):
    if x<points[0]['T_C'] or x>points[-1]['T_C']:
        raise ValueError('material_temperature_range')
    for a,b in zip(points,points[1:]):
        if a['T_C']<=x<=b['T_C']:
            t=(x-a['T_C'])/(b['T_C']-a['T_C'])
            return a[key]+t*(b[key]-a[key])
    return points[-1][key]

def sps_segments(V1,V2,f,L,P,Lm):
    # phi = pi*D; low-phase branch. Zero-mean half-wave symmetric solution.
    q=2*f*L*abs(P)/(V1*V2)
    if q>.25:
        raise ValueError('power_unreachable')
    D=(1-math.sqrt(1-4*q))/2
    T=1/f;d=D*T/2
    ts=[0,d,T/2,T/2+d,T]
    vs=[(V1,-V2),(V1,V2),(-V1,V2),(-V1,-V2)]
    slopes=[(a-b)/L for a,b in vs]
    half_rise=sum(slopes[k]*(ts[k+1]-ts[k]) for k in [0,1])
    i0=-half_rise/2;im0=-V1/(4*f*Lm)
    seg=[];i=i0;im=im0
    for k,(v1,v2) in enumerate(vs):
        dt=ts[k+1]-ts[k]
        j=i+slopes[k]*dt;jm=im+v1/Lm*dt
        seg.append((ts[k],dt,i,j,im,jm,v1,v2))
        i,im=j,jm
    def rms_sum(a,b):
        return math.sqrt(sum(dt*(a(x)**2+a(x)*b(x)+b(x)**2)/3 for x in seg for dt in [x[1]])/T)
    it=rms_sum(lambda x:x[2],lambda x:x[3])
    ip=rms_sum(lambda x:x[2]+x[4],lambda x:x[3]+x[5])
    power=sum(x[1]*x[6]*(x[2]+x[3])/2 for x in seg)/T
    avg=sum(x[1]*(x[2]+x[3])/2 for x in seg)/T
    assert abs(power-abs(P))<=max(1e-6,abs(P)*1e-9)
    assert abs(i-i0)<1e-8 and abs(im-im0)<1e-8 and abs(avg)<1e-8
    return D,seg,it,ip

def sampled_spectrum(seg,f,n,N=512):
    # Midpoint quadrature; 128 harmonics max, frequency-validity checked per op.
    values_p=[];values_s=[];k=0;T=1/f
    for z in range(N):
        t=(z+.5)*T/N
        while k<len(seg)-1 and t>=seg[k][0]+seg[k][1]:k+=1
        ta,dt,ia,ib,ima,imb,*_=seg[k]
        r=0 if dt==0 else (t-ta)/dt
        it=ia+(ib-ia)*r;im=ima+(imb-ima)*r
        values_p.append(it+im);values_s.append(n*it)
    out=[]
    for h in range(1,129):
        weights=[complex(math.cos(2*math.pi*h*(z+.5)/N),-math.sin(2*math.pi*h*(z+.5)/N)) for z in range(N)]
        a=sum(v*w for v,w in zip(values_p,weights))/N
        b=sum(v*w for v,w in zip(values_s,weights))/N
        out.append((h,2*abs(a)**2,2*abs(b)**2))
    return out

def winding(N,wire,parallel,h,layer_t,clearance,start,core):
    dia=wire['outer_diameter_mm']+wire['outer_dimension_tolerance_mm']+clearance
    per_layer=math.floor(h/dia)
    if per_layer<1:raise ValueError('geometry_no_turn_per_layer')
    counts=[];remain=N
    while remain:
        counts.append(min(per_layer,remain));remain-=counts[-1]
    thickness=len(counts)*parallel*dia+(len(counts)-1)*layer_t
    mlt=[]
    # Radial parallel bundles: independent branch lengths, averaged in demo.
    for j,cnt in enumerate(counts):
        centers=[start+j*(parallel*dia+layer_t)+(p+.5)*dia for p in range(parallel)]
        mlt.append(sum(2*(core['leg_width_mm']+core['leg_depth_mm'])+8*x for x in centers)/parallel)
    branch_length=sum(a*b for a,b in zip(counts,mlt))/1000+.15
    rdc=wire['Rdc_ohm_per_m_20C']*branch_length/parallel+.00005/parallel
    return dict(turns=N,layers=len(counts),turns_per_layer=counts,thickness_mm=thickness,
        mean_turn_length_mm=sum(a*b for a,b in zip(counts,mlt))/N,
        branch_length_m=branch_length,Rdc_20C_ohm=rdc,
        Acu_mm2=wire['copper_area_mm2']*parallel,parallel_bundles=parallel,
        wire_id=wire['id'],mass_kg=wire['mass_kg_per_m']*branch_length*parallel)

def evaluate(inp,db,genes):
    mats,cores,wires,ins,layouts,models,rules=db
    cid,Np,pid,sid,pp,ps,nins=genes
    c=cores[cid];mat=mats[c['material_id']];layout=layouts['DEMO_LAYOUT_PS']
    Ns=Np//2;n=Np/Ns;lim=inp['design_rules'];ind=inp['inductance']
    # Demo enumerates exact 2:1 turns only. No automatic voltage-ratio override.
    nominal=inp['operating_points'][0]['V1_dc_V']/inp['operating_points'][0]['V2_dc_V']
    if abs(n/nominal-1)>lim['turns_ratio_error_max']:raise ValueError('turns_ratio')
    rule=rules[lim['rule_set_id']]
    dps=nins*ins[layout['main_insulation_id']]['thickness_mm']
    if dps<rule['main_insulation_min_mm']:raise ValueError('insulation_rule')
    h=c['window_height_mm']-2*c['end_margin_each_mm']
    lp=ins[layout['layer_insulation_id']]['thickness_mm']
    p=winding(Np,wires[pid],pp,h,lp,layout['process_clearance_mm'],c['bobbin_wall_mm'],c)
    s=winding(Ns,wires[sid],ps,h,lp,layout['process_clearance_mm'],c['bobbin_wall_mm']+p['thickness_mm']+dps,c)
    radial=c['bobbin_wall_mm']+p['thickness_mm']+dps+s['thickness_mm']+c['radial_margin_mm']
    if radial>c['window_width_mm']:raise ValueError('geometry_window_width')
    Ae=c['Ae_mm2']*1e-6
    Lm=MU0*Np*Np*Ae/(c['le_mm']*.001/mat['mu_e'])
    if Lm<ind['Lm_min_H']:raise ValueError('Lm_min')
    mlt=(p['mean_turn_length_mm']+s['mean_turn_length_mm'])/2000
    L=MU0*Np*Np*mlt/(h*.001)*((p['thickness_mm']+s['thickness_mm'])/3+dps)*.001
    if abs(L/ind['L_series_target_H']-1)>ind['relative_tolerance']:raise ValueError('leakage_tolerance')
    volume=math.prod(c['core_outer_mm'])*1e-6
    mass=c['mass_kg']+p['mass_kg']+s['mass_kg']+.2 # explicit synthetic assembly allowance
    if volume>lim['volume_max_L']:raise ValueError('volume_max')
    if mass>lim['mass_max_kg']:raise ValueError('mass_max')
    thermal=models[inp['cooling']['thermal_model_id']]
    Gc=1/thermal['Rca_K_W'];Gw=1/thermal['Rwa_K_W'];Gx=1/thermal['Rcw_K_W']
    determinant=(Gc+Gx)*(Gw+Gx)-Gx*Gx
    out=[]
    for op in inp['operating_points']:
        f=op['fs_Hz'];B=op['V1_dc_V']/(4*f*Np*Ae)
        rg=mat['valid_range']
        if not(rg['f_Hz'][0]<=f<=rg['f_Hz'][1] and rg['Bpk_T'][0]<=B<=rg['Bpk_T'][1]):raise ValueError('core_model_range')
        D,seg,it,ip=sps_segments(op['V1_dc_V'],n*op['V2_dc_V'],f,L,op['P_req_W'],Lm)
        is_=n*it
        if ip/p['Acu_mm2']>lim['Jp_max_A_per_mm2'] or is_/s['Acu_mm2']>lim['Js_max_A_per_mm2']:raise ValueError('current_density')
        spectrum=sampled_spectrum(seg,f,n)
        fr=models['DEMO_FR_EMPIRICAL']
        def factor(freq,w):
            return max(1,fr['base_Fr']*(freq/20000)**fr['frequency_exponent']+fr['additional_Fr_per_extra_layer']*(w['layers']-1))
        # In synthetic demo only, Fr function extends across harmonics; extrapolation is explicit.
        wp=sum(a*factor(k*f,p) for k,a,b in spectrum)
        ws=sum(b*factor(k*f,s) for k,a,b in spectrum)
        covered_p=sum(a for k,a,b in spectrum);covered_s=sum(b for k,a,b in spectrum)
        tail_p=max(0,ip**2-covered_p);tail_s=max(0,is_**2-covered_s)
        wp+=tail_p*factor(129*f,p);ws+=tail_s*factor(129*f,s)
        tc=tw=op['T_amb_C'];param=mat['loss_parameters'];last=None
        for iteration in range(50):
            if not rg['T_C'][0]<=tc<=rg['T_C'][1]:raise ValueError('material_temperature_range')
            pc=param['ki']*(4*f*B)**param['alpha']*(2*B)**(param['beta']-param['alpha'])*c['Ve_mm3']*1e-9
            pc*=1+param['temperature_coefficient_per_K']*(tc-param['reference_temperature_C'])
            rtemp=1+.00393*(tw-20)
            cp=wp*p['Rdc_20C_ohm']*rtemp;cs=ws*s['Rdc_20C_ohm']*rtemp;cw=cp+cs
            ntc=op['T_amb_C']+(pc*(Gw+Gx)+cw*Gx)/determinant
            ntw=op['T_amb_C']+(cw*(Gc+Gx)+pc*Gx)/determinant
            total=pc+cw
            if max(abs(ntc-tc),abs(ntw-tw))<.005 and last is not None and abs(total-last)/total<.0001:
                tc,tw=ntc,ntw;break
            tc=(tc+ntc)/2;tw=(tw+ntw)/2;last=total
        else:raise ValueError('thermal_not_converged')
        if B>interpolate(mat['Bsat_vs_T'],tc,'Bsat_T')*mat['B_derating']:raise ValueError('flux_limit')
        if tw>lim['Tw_max_C'] or tc>lim['Tc_max_C'] or tw-op['T_amb_C']>lim['deltaT_w_max_K']:raise ValueError('temperature_limit')
        out.append(dict(point_id=op['id'],phase_D=D,phase_rad=D*math.pi,Bpk_T=B,
            Ip_rms_A=ip,Is_rms_A=is_,Jp_A_mm2=ip/p['Acu_mm2'],Js_A_mm2=is_/s['Acu_mm2'],
            Pcore_W=pc,Pcu_p_W=cp,Pcu_s_W=cs,Ptotal_W=total,Tc_est_C=tc,Tw_est_C=tw,
            deltaT_w_K=tw-op['T_amb_C'],Thotspot_est_C=None,
            spectrum_tail_current_energy_fraction_p=tail_p/ip**2,
            thermal_iterations=iteration+1))
    A_overlap=mlt*h*.001
    C=EPS0*ins[layout['main_insulation_id']]['epsilon_r']*A_overlap/(dps*.001)
    return dict(candidate_id=hashlib.sha256(str(genes).encode()).hexdigest()[:12],
        result_grade='demo_only',data_status='synthetic',core_id=cid,material_id=mat['id'],
        layout_id=layout['id'],Np=Np,Ns=Ns,n=n,gap_equivalent_mm=0,dps_mm=dps,
        primary=p,secondary=s,Lm_p_H=Lm,Lleak_p_H=L,Lseries_p_H=L,Lext_p_H=0,
        volume_envelope_L=volume,mass_kg=mass,Cps_estimate_F=C,
        hotspot_status='not_available',insulation_status='demo_rule_check_only',
        points=out,objectives=[out[0]['Ptotal_W'],volume],
        model_warnings=['All values are fictional; no engineering qualification',
            'Synthetic Fr is extrapolated to harmonics; residual energy assigned last-harmonic Fr',
            'Vmag approximated by V1_dc; leakage split/induced-voltage model omitted',
            'Shared synthetic thermal network; no hotspot or dielectric qualification'])

def validate_input(inp):
    if inp['data_mode']!='demo':raise ValueError('SYNTHETIC_DATA_BLOCKED_IN_ENGINEERING')
    if inp['topology']!='DAB_SPS' or inp['bridge_duty']!=.5:raise ValueError('UNSUPPORTED_WAVEFORM')
    if inp['inductance']['leakage_mode']!='integrated':raise ValueError('DEMO_SUPPORTS_INTEGRATED_ONLY')
    if inp['search']['allowed_layouts']!=['DEMO_LAYOUT_PS']:raise ValueError('DEMO_SUPPORTS_PS_ONLY')
    for op in inp['operating_points']:
        if min(op[k] for k in ['V1_dc_V','V2_dc_V','P_req_W','fs_Hz'])<=0:raise ValueError('NONPOSITIVE_INPUT')

def run(inp,outdir):
    validate_input(inp);db=validate_database();_,cores,wires,_,layouts,*_=db
    search=inp['search'];fail=Counter();feasible=[];count=0
    # Deterministic full enumeration is the reference, not an NSGA-II implementation.
    choices=itertools.product(cores,range(search['Np_min'],search['Np_max']+1,search['Np_step']),
        wires,wires,range(1,search['parallel_bundles_max']+1),range(1,search['parallel_bundles_max']+1),
        layouts['DEMO_LAYOUT_PS']['main_insulation_layers_choices'])
    for genes in choices:
        count+=1
        try:feasible.append(evaluate(inp,db,genes))
        except ValueError as e:fail[str(e)]+=1
    # Two objectives; retain one representative per numerically identical objective pair.
    front=[];seen=set()
    for c in sorted(feasible,key=lambda x:tuple(x['objectives'])):
        pair=tuple(round(v,9) for v in c['objectives'])
        if pair in seen:continue
        seen.add(pair)
        if any(a['objectives'][0]<=c['objectives'][0] and a['objectives'][1]<=c['objectives'][1] for a in front):continue
        front.append(c)
    summary=dict(status='completed' if front else 'no_feasible_solution',data_mode='demo',
        pipeline='data_checks/integer_candidates/packing/inductance/SPS_current/loss/thermal/constraints/Pareto/export',
        optimizer='full_enumeration_reference',candidate_count=count,feasible_count=len(feasible),
        pareto_count=len(front),failure_counts=dict(fail),pareto=front,
        data_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in BASE.glob('*library.json')})
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (outdir/'pareto.csv').open('w',encoding='utf-8-sig',newline='') as fh:
        keys=['candidate_id','core_id','Np','Ns','dps_mm','Lleak_p_H','volume_envelope_L','Ptotal_W','Tw_est_C']
        writer=csv.DictWriter(fh,fieldnames=keys);writer.writeheader()
        for c in front:
            row={k:c[k] for k in keys if k in c};row.update({k:c['points'][0][k] for k in ['Ptotal_W','Tw_est_C']});writer.writerow(row)
    report=['# 虚构数据流程验证报告','', '**所有数值仅用于软件流程验证，不用于工程设计。**','',
        f"枚举候选：{count}；可行：{len(feasible)}；Pareto 代表点：{len(front)}。",'',
        '| 磁芯 | 匝数 P/S | 主绝缘 mm | 漏感 μH | 损耗 W | 体积 L | 绕组节点 ℃ |',
        '|---|---|---|---|---|---|---|']
    for c in front:
        o=c['points'][0]
        report.append(f"|{c['core_id']}|{c['Np']}/{c['Ns']}|{c['dps_mm']}|{c['Lleak_p_H']*1e6:.2f}|{o['Ptotal_W']:.1f}|{c['volume_envelope_L']:.2f}|{o['Tw_est_C']:.1f}|")
    report+=['','本脚本以完全枚举验证计算与筛选链路；不是生产软件或 NSGA-II 算法验收。',
             '高频电阻、热阻、绝缘距离和磁芯损耗系数均为合成参数；结果不能据此判断真实产品可行性。']
    (outdir/'report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',default='sample_input_feasible.json')
    parser.add_argument('--output',default='run_output');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:
        result=run(load('sample_input_feasible.json'),BASE/'reference_output')
        assert result['feasible_count']>0 and result['pareto_count']>0
        no=run(load('sample_input_infeasible.json'),BASE/'reference_no_feasible')
        assert no['feasible_count']==0 and no['status']=='no_feasible_solution'
        blocked=[]
        for filename in ['sample_input_engineering_blocked.json','sample_input_unsupported.json']:
            try:validate_input(load(filename))
            except ValueError as e:blocked.append(str(e))
            else:raise AssertionError(filename)
        checks=dict(database_checks='passed',feasible_case='passed',infeasible_case='passed',
            engineering_guard='passed',waveform_guard='passed',blocked_errors=blocked,
            candidate_count=result['candidate_count'],feasible_count=result['feasible_count'],pareto_count=result['pareto_count'])
        (BASE/'self_test_results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(checks,ensure_ascii=False))
    else:
        file=Path(args.input);file=file if file.is_absolute() else BASE/file
        result=run(json.loads(file.read_text(encoding='utf-8')),BASE/args.output)
        print(json.dumps({k:v for k,v in result.items() if k not in ['pareto','data_hashes']},ensure_ascii=False))

if __name__=='__main__':main()
