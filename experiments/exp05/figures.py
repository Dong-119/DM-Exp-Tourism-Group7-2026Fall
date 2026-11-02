"""条件建议的分类统计图与流程图。"""
import numpy as np


PALETTE = {'dataset_corpus': '#3E6783', 'editorial_route_guide': '#609C94',
           'official_route_facts': '#BBC6CD', 'synthetic_teaching': '#C59169'}


def generate(folder, rows, stats):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib import font_manager
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import FancyBboxPatch, Rectangle, PathPatch
    from matplotlib.path import Path
    from experiment import ORIGINS, SCOPES
    installed={font.name for font in font_manager.fontManager.ttflist}
    chinese=next((name for name in ['SimSun','Noto Serif CJK SC','Source Han Serif SC',
                                  'Microsoft YaHei','WenQuanYi Zen Hei'] if name in installed),'DejaVu Sans')
    english='Times New Roman' if 'Times New Roman' in installed else 'DejaVu Serif'
    cn = FontProperties(family=chinese)
    bold = FontProperties(family=chinese, weight='bold')
    plt.rcParams.update({'font.family':english, 'font.size':10,
                         'axes.unicode_minus':False, 'svg.fonttype':'none',
                         'axes.edgecolor':'#A8B4BA', 'axes.linewidth':.7})
    ink, muted, grid = '#243E4D', '#697C85', '#E5ECEF'
    origins = list(ORIGINS)
    def text(ax, x, y, s, size=10, color=ink, weight=False, **kwargs):
        return ax.text(x, y, s, fontproperties=bold if weight else cn, fontsize=size, color=color, **kwargs)
    def save(fig, name):
        fig.savefig(folder / (name+'.png'), dpi=240, bbox_inches='tight', facecolor='white')
        fig.savefig(folder / (name+'.svg'), bbox_inches='tight', facecolor='white')
        plt.close(fig)
    def legend(fig, y=.92):
        from matplotlib.lines import Line2D
        handles = [Line2D([], [], marker='s', linestyle='', markersize=7,
                          color=PALETTE[o], label=ORIGINS[o]) for o in origins]
        fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5,y), ncol=4,
                   frameon=False, prop=FontProperties(family=chinese,size=9),
                   handletextpad=.4, columnspacing=1.8)

    # 游客类型按来源堆叠，右侧展示人群限定覆盖。
    labels = ['亲子','老人','摄影爱好者','行动不便','情侣','自由行','青年']
    fig = plt.figure(figsize=(8.6,4.15))
    gs = fig.add_gridspec(1,2,width_ratios=[2.25,1],left=.11,right=.97,bottom=.17,top=.76,wspace=.24)
    ax, overview = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    left = np.zeros(len(labels))
    for origin in origins:
        values = np.array([sum(r['provenance_kind']==origin and label in r['visitor_types'] for r in rows) for label in labels])
        ax.barh(np.arange(len(labels)),values,left=left,height=.52,color=PALETTE[origin],edgecolor='white',linewidth=.5,zorder=3)
        left += values
    for i,total in enumerate(left):
        ax.text(total+.22,i,str(int(total)),va='center',fontsize=10,color=ink)
    ax.set_yticks(np.arange(len(labels)),labels,fontproperties=cn,fontsize=11)
    ax.invert_yaxis(); ax.set_xlim(0,max(left)+2); ax.set_xticks([0,5,10,15])
    ax.grid(axis='x',color=grid,linewidth=.7,zorder=0)
    ax.spines[['top','right','left']].set_visible(False); ax.tick_params(axis='y',length=0)
    ax.set_xlabel('建议条数',fontproperties=cn,fontsize=10)
    text(ax,0,1.06,'(a) 明确人群的建议构成',11,weight=True,transform=ax.transAxes)
    unspecified = sum(r['visitor_types']==['未特定'] for r in rows)
    specified = len(rows)-unspecified
    overview.pie([specified,unspecified],colors=[PALETTE['dataset_corpus'],'#E8EEF1'],
                 startangle=90,counterclock=False,wedgeprops={'width':.23,'edgecolor':'white','linewidth':2})
    overview.text(0,.08,str(len(rows)),ha='center',va='center',fontsize=28,color=ink)
    text(overview,0,-.24,'主体建议',10,ha='center')
    text(overview,.5,1.06,'(b) 人群限定覆盖',11,weight=True,ha='center',transform=overview.transAxes)
    text(overview,.5,-.07,f'明确人群  {specified}条 · {specified/len(rows):.1%}',10,ha='center',transform=overview.transAxes)
    text(overview,.5,-.23,f'未特定  {unspecified}条 · {unspecified/len(rows):.1%}',10,color=muted,ha='center',transform=overview.transAxes)
    fig.suptitle('游客画像与条件建议覆盖',fontproperties=bold,fontsize=14,color=ink,y=.99)
    legend(fig,.93)
    fig.text(.11,.025,f'注：左图允许多标签，同一建议可计入多类；右图按建议组计数，合计为{len(rows)}条。',fontproperties=cn,fontsize=9,color=muted)
    save(fig,'游客类型统计')

    # 条件类型×来源矩阵：绝对数量统一映射色阶，右侧显示各类总量。
    conditions = sorted(stats['by_condition_type'],key=lambda k:-stats['by_condition_type'][k])
    matrix = np.array([[sum(r['condition_type']==kind and r['provenance_kind']==origin for r in rows) for origin in origins] for kind in conditions])
    totals = matrix.sum(axis=1)
    fig = plt.figure(figsize=(8.6,4.7))
    gs = fig.add_gridspec(1,2,width_ratios=[4,1.8],left=.16,right=.96,bottom=.17,top=.82,wspace=.18)
    ax, totalax = fig.add_subplot(gs[0]),fig.add_subplot(gs[1])
    cmap = LinearSegmentedColormap.from_list('paper_teal',['#F8FAFB','#D8E9E7','#83B4AE','#366E76'])
    ax.imshow(matrix,cmap=cmap,vmin=0,vmax=max(1,matrix.max()),aspect='auto')
    ax.set_xticks(range(4),['原语料游记','路线整理稿','官方路线\n事实重述','教学模拟'],fontproperties=cn,fontsize=10)
    ax.set_yticks(range(len(conditions)),conditions,fontproperties=cn,fontsize=11)
    ax.tick_params(length=0,pad=9)
    for y in range(len(conditions)):
        for x in range(4):
            count = matrix[y,x]
            ax.text(x,y,str(count),ha='center',va='center',fontsize=11,
                    color='white' if count>matrix.max()*.62 else ink if count else '#A7B3B9')
    ax.set_xticks(np.arange(-.5,4,1),minor=True); ax.set_yticks(np.arange(-.5,len(conditions),1),minor=True)
    ax.grid(which='minor',color='white',linewidth=3); ax.tick_params(which='minor',length=0)
    for spine in ax.spines.values(): spine.set_visible(False)
    totalax.hlines(range(len(conditions)),0,totals,color='#D8E1E5',linewidth=2,zorder=1)
    totalax.scatter(totals,range(len(conditions)),s=38,color=PALETTE['dataset_corpus'],zorder=3)
    for y,n in enumerate(totals): totalax.text(n+1,y,str(n),va='center',fontsize=11,color=ink)
    totalax.set_ylim(len(conditions)-.5,-.5); totalax.set_xlim(0,max(totals)*1.22)
    totalax.set_yticks([]); totalax.set_xticks([0,10,20,30]); totalax.grid(axis='x',color=grid,linewidth=.6)
    totalax.spines[['top','right','left']].set_visible(False)
    totalax.set_xlabel('各类合计',fontproperties=cn,fontsize=10)
    text(ax,0,1.12,'(a) 来源构成',11,weight=True,transform=ax.transAxes)
    text(totalax,0,1.12,'(b) 数量对比',11,weight=True,transform=totalax.transAxes)
    fig.suptitle('不同来源中的条件类型分布',fontproperties=bold,fontsize=14,color=ink,y=.98)
    fig.text(.16,.035,'注：单元格数字为建议条数，颜色深浅使用同一尺度；按主要条件类型计数。',fontproperties=cn,fontsize=9,color=muted)
    save(fig,'条件类型统计')

    # 来源性质→实际适用地点。带宽按条数同比例编码，零值来源单独标注。
    active = [o for o in origins if stats['by_provenance'][o]]
    flow = {o:{s:sum(r['provenance_kind']==o and r['target_scope']==s for r in rows) for s in SCOPES} for o in active}
    assert sum(sum(values.values()) for values in flow.values()) == len(rows)
    fig,ax=plt.subplots(figsize=(8.6,4.15)); ax.set_xlim(0,1);ax.set_ylim(0,1);ax.axis('off')
    unit=.0067; left_nodes={}; right_nodes={}; cursor=.86
    for origin in active:
        n=sum(flow[origin].values()); h=n*unit; left_nodes[origin]=(cursor-h,cursor);cursor-=h+.055
    cursor=.86
    for scope in SCOPES:
        n=sum(flow[o][scope] for o in active);h=n*unit;right_nodes[scope]=(cursor-h,cursor);cursor-=h+.04
    lcursor={o:left_nodes[o][1] for o in active};rcursor={s:right_nodes[s][1] for s in SCOPES}
    x0,x1=.275,.76
    for origin in active:
        for scope in SCOPES:
            n=flow[origin][scope]
            if not n: continue
            upper0,upper1=lcursor[origin],rcursor[scope];lower0,lower1=upper0-n*unit,upper1-n*unit
            verts=[(x0,upper0),(x0+.22,upper0),(x1-.22,upper1),(x1,upper1),
                   (x1,lower1),(x1-.22,lower1),(x0+.22,lower0),(x0,lower0),(x0,upper0)]
            codes=[Path.MOVETO,Path.CURVE4,Path.CURVE4,Path.CURVE4,Path.LINETO,
                   Path.CURVE4,Path.CURVE4,Path.CURVE4,Path.CLOSEPOLY]
            ax.add_patch(PathPatch(Path(verts,codes),facecolor=PALETTE[origin],edgecolor='white',lw=.5,alpha=.47))
            lcursor[origin]=lower0;rcursor[scope]=lower1
    for origin,(low,high) in left_nodes.items():
        ax.add_patch(Rectangle((x0-.018,low),.018,high-low,color=PALETTE[origin],lw=0))
        text(ax,x0-.033,(low+high)/2,ORIGINS[origin]+'\n'+str(sum(flow[origin].values()))+' 条',11,ha='right',va='center')
    for scope,(low,high) in right_nodes.items():
        ax.add_patch(Rectangle((x1,low),.018,high-low,color='#617C8C',lw=0))
        text(ax,x1+.035,(low+high)/2,scope+'  '+str(sum(flow[o][scope] for o in active)),11,va='center')
    text(ax,x0,.94,'来源性质',11,weight=True,ha='center');text(ax,x1,.94,'实际适用地点',11,weight=True,ha='center')
    fig.suptitle('建议来源与实际适用范围',fontproperties=bold,fontsize=14,color=ink,y=.99)
    fig.text(.12,.018,'注：带宽与建议条数成比例；官方路线事实重述未抽出条件建议（0条），不绘制流带。',fontproperties=cn,fontsize=9,color=muted)
    save(fig,'来源与适用范围')

    # 六个处理步骤按蛇形顺序排布。
    def draw_compact_process_flow():
        from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea

        colors = {'blue': '#375C75', 'teal': '#52877F', 'brown': '#AA7B55'}
        ink_flow, muted_flow = '#2B424F', '#617782'
        arrow_color = '#95A8B2'
        face = {'blue': '#F4F7FA', 'teal': '#F2F7F6', 'brown': '#FAF6F2'}

        fig, ax = plt.subplots(figsize=(10, 3.36))
        fig.subplots_adjust(left=.008, right=.992, bottom=.018, top=.982)
        ax.set_xlim(0, 10.05)
        ax.set_ylim(0, 3.33)
        ax.axis('off')

        xs = [.10, 3.60, 7.10]
        width, height = 2.85, 1.34
        top, bottom = 1.87, .12

        def add_card(x, y, step, heading, color):
            ax.add_patch(FancyBboxPatch(
                (x, y), width, height,
                boxstyle='round,pad=.008,rounding_size=.095',
                facecolor=face[color], edgecolor='#CDD9E0', linewidth=1.0))
            ax.plot([x + .14, x + .14], [y + .16, y + height - .16],
                    color=colors[color], linewidth=3.0, solid_capstyle='round')
            ax.text(x + .32, y + 1.06, step, color=muted_flow,
                    fontproperties=FontProperties(family=english, size=12.5),
                    va='center')
            ax.text(x + .72, y + 1.06, heading, color=ink_flow,
                    fontproperties=FontProperties(family=chinese, weight='bold', size=17),
                    va='center')

        def add_primary_metric(x, y, value, unit, color):
            number = TextArea(str(value), textprops={
                'fontproperties': FontProperties(
                    family=english, weight='bold', size=36),
                'color': colors[color],
            })
            suffix = TextArea(unit, textprops={
                'fontproperties': FontProperties(family=chinese, size=14),
                'color': muted_flow,
            })
            metric = HPacker(children=[number, suffix], align='baseline', pad=0, sep=8)
            ax.add_artist(AnnotationBbox(
                metric, (x + .34, y + .49), xycoords='data',
                box_alignment=(0, .5), frameon=False))

        def add_pair_metrics(x, y, left_value, right_value,
                             left_label, right_label, color, divider=False):
            center_y = y + .64
            label_y = y + .20
            left_x, right_x = x + .82, x + 2.22
            if divider:
                ax.plot([x + 1.52, x + 1.52], [y + .43, y + .86],
                        color='#D6DFE4', linewidth=.9)
            for value, center in ((left_value, left_x), (right_value, right_x)):
                ax.text(center, center_y, str(value), ha='center', va='center',
                        color=colors[color],
                        fontproperties=FontProperties(
                            family=english, weight='bold', size=32))
            if not divider:
                ax.text(x + 1.52, y + .64, '+', ha='center', va='center',
                        color='#99AAB3',
                        fontproperties=FontProperties(family=english, size=20))
            ax.text(left_x, label_y, left_label, ha='center', va='center',
                    color=muted_flow, fontproperties=FontProperties(family=chinese, size=14))
            ax.text(right_x, label_y, right_label, ha='center', va='center',
                    color=muted_flow, fontproperties=FontProperties(family=chinese, size=14))

        add_card(xs[0], top, '01', '实验一正文', 'blue')
        add_card(xs[1], top, '02', '句段切分', 'blue')
        add_card(xs[2], top, '03', '条件抽取', 'teal')
        add_card(xs[2], bottom, '04', '原文校验', 'brown')
        add_card(xs[1], bottom, '05', '关系补充', 'teal')
        add_card(xs[0], bottom, '06', '建议映射', 'blue')

        input_stats = stats.get('input', {})
        add_primary_metric(xs[0], top, input_stats.get('records', 48), '篇', 'blue')
        add_primary_metric(xs[1], top, input_stats.get('sentences', 1406), '句段', 'blue')
        add_primary_metric(xs[2], top, stats.get('rule_candidates', 90), '条候选', 'teal')

        decisions = stats.get('candidate_counts', {})
        kept = decisions.get('accept', 0) + decisions.get('correct', 0)
        excluded = decisions.get('exclude', 17)
        add_pair_metrics(xs[2], bottom, kept, excluded, '保留', '排除', 'brown', divider=True)
        add_pair_metrics(xs[1], bottom,
                         stats.get('additional_source_pairs', 26),
                         stats.get('contextual_pairs', 6),
                         '原语料建议', '上下文补充', 'teal')
        add_pair_metrics(xs[0], bottom,
                         stats.get('main_after_dedup', len(rows)),
                         stats.get('outside_scope', 10),
                         '主体建议', '其他地点', 'blue')

        def add_arrow(start, end):
            ax.annotate('', xy=end, xytext=start, arrowprops={
                'arrowstyle': '-|>', 'color': arrow_color, 'linewidth': 1.4,
                'mutation_scale': 13, 'shrinkA': 0, 'shrinkB': 0,
                'capstyle': 'round', 'joinstyle': 'round',
            })

        top_y, bottom_y = top + .67, bottom + height / 2
        add_arrow((xs[0] + width + .08, top_y), (xs[1] - .10, top_y))
        add_arrow((xs[1] + width + .08, top_y), (xs[2] - .10, top_y))
        add_arrow((xs[2] + width / 2, top - .075),
                  (xs[2] + width / 2, bottom + height + .075))
        add_arrow((xs[2] - .10, bottom_y), (xs[1] + width + .08, bottom_y))
        add_arrow((xs[1] - .10, bottom_y), (xs[0] + width + .08, bottom_y))

        for extension in ['png', 'svg']:
            fig.savefig(folder / f'条件建议抽取流程.{extension}', dpi=320,
                        bbox_inches='tight', pad_inches=.09, facecolor='white')
        plt.close(fig)

    draw_compact_process_flow()
