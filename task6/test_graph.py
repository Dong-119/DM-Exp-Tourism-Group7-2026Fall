"""回归检查上游路线事件、来源聚合和导出结构的一致性。"""
import json
import unittest
from collections import Counter
from pathlib import Path
import networkx as nx
from run_experiment import load_graph, load_json, ROUTE_INPUT, ENTITY_INPUT, ADVICE_INPUT, OUTPUT, EDGE_TYPES, node_id


class GraphRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, _ = load_graph()

    def test_every_route_event_survives(self):
        for route in load_json(ROUTE_INPUT):
            actual = sorted((edge['order'], self.graph.nodes[target]['label']) for _, target, edge in self.graph.out_edges(node_id('route', route['route_id']), data=True) if edge['relation'] == 'visits')
            self.assertEqual(actual, [(step['order'], step['poi']) for step in route['steps']])

    def test_every_route_transition_survives(self):
        expected = Counter()
        for route in load_json(ROUTE_INPUT):
            for left, right in zip(route['steps'], route['steps'][1:]):
                expected[(route['route_id'], right['order'], left['poi'], right['poi'])] += 1
        actual = Counter((edge['route_id'], edge['order'], self.graph.nodes[source]['label'], self.graph.nodes[target]['label']) for source, target, edge in self.graph.edges(data=True) if edge['relation'] == 'next')
        self.assertEqual(actual, expected)

    def test_merged_mentions_preserve_all_documents(self):
        expected = set()
        for document in load_json(ENTITY_INPUT):
            if document.get('scenic_name') == '颐和园' and any((entity.get('canonical') or entity.get('text')) == '佛香阁' for entity in document.get('entities', [])):
                expected.add(document['doc_id'])
        edge = self.graph['scenic:颐和园']['poi:颐和园:佛香阁']['mentions_poi']
        self.assertEqual(set(edge['source_documents']), expected)
        self.assertEqual(len(expected), 16)

    def test_synthetic_advice_stays_identifiable(self):
        for advice in load_json(ADVICE_INPUT):
            actual = self.graph.nodes['advice:' + advice['mapping_id']]
            self.assertEqual(actual['provenance_kind'], advice['provenance_kind'])
            self.assertEqual(actual['source_document'], advice['doc_id'])

    def test_mentions_do_not_become_membership(self):
        self.assertFalse(self.graph.has_edge('scenic:天坛', 'poi:天坛:故宫', key='contains'))
        self.assertTrue(self.graph.has_edge('scenic:天坛', 'poi:天坛:故宫', key='mentions_poi'))

    def test_json_and_graphml_preserve_event_counts(self):
        data = json.loads((OUTPUT / 'knowledge_graph.json').read_text(encoding='utf-8'))
        graphml = nx.read_graphml(OUTPUT / 'knowledge_graph.graphml', force_multigraph=True)
        self.assertEqual(graphml.number_of_edges(), self.graph.number_of_edges())
        self.assertEqual(sum(edge['relation'] == 'visits' for edge in data['edges']), 39)
        self.assertEqual(set(edge['relation'] for edge in data['edges']), set(EDGE_TYPES))


if __name__ == '__main__':
    unittest.main(verbosity=2)
