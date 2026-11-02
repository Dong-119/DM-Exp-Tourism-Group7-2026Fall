"""运行实验五，生成条件建议映射表、统计和图表。"""
import argparse
import json
from experiment import run
from evaluate_rules import evaluate

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-plots',action='store_true',help='只生成数据和结果页面')
    args=parser.parse_args()
    stats=run(make_plots=not args.no_plots)
    evaluate()
    print(json.dumps(stats,ensure_ascii=False,indent=2))
