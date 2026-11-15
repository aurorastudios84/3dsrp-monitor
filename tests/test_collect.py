import copy
import unittest
from unittest.mock import patch
import urllib.error
import collect

class CollectorTests(unittest.TestCase):
    def test_deduplicates_reddit_tracking_links(self):
        first='https://www.reddit.com/r/3dspiracy/comments/abc123/title/?utm_source=share'
        second='https://reddit.com/comments/abc123'
        self.assertEqual(collect.canonical(first),collect.canonical(second))
        self.assertEqual(collect.canonical('https://www.google.com/url?q=https%3A%2F%2Fexample.com%2Fpost'), 'https://example.com/post')
        with self.assertRaises(ValueError):
            collect.canonical('javascript:alert(1)')

    def test_installer_groups_exclude_source(self):
        for name, group in [('3DSRP-New3DS.cia','New 3DS'),('3DSRP-Relay.3dsx','Relay'),('3DSRP-Companion.apk','Android companion'),('3DSRP-Companion.exe','Windows companion'),('3DSRP-Source.tar.gz','Other / source')]:
            self.assertEqual(collect.asset_group(name),group)

    def test_failed_source_retains_data_and_redacts_secret(self):
        state={'sources':{},'mentions':{'old':{'title':'existing'}}}
        def failed():
            state['mentions'].clear()
            raise urllib.error.HTTPError('https://example.com?key=SECRET',403,'secret details',{},None)
        collect.source(state,'YouTube',failed)
        self.assertIn('old',state['mentions'])
        self.assertEqual(state['sources']['YouTube']['status'],'error')
        self.assertNotIn('SECRET',str(state))

    def test_daily_snapshots_are_idempotent(self):
        state={'mentions':{},'sources':{},'history':[]}
        release=[{'tag_name':'v1','assets':[{'id':1,'name':'build.cia','download_count':12,'browser_download_url':'https://example.com/a'}, {'id':2,'name':'source.tar.gz','download_count':8,'browser_download_url':'https://example.com/b'}]}]
        with patch.object(collect,'api',side_effect=[{'stargazers_count':2,'forks_count':1},release,{'stargazers_count':3,'forks_count':1},release]):
            collect.collect_github(state,{'repository':'owner/repo'})
            collect.collect_github(state,{'repository':'owner/repo'})
        self.assertEqual(len(state['history']),1)
        self.assertEqual(state['history'][0]['stars'],3)
        self.assertEqual(state['history'][0]['downloads'],12)

    def test_traffic_updates_partial_day_without_double_counting(self):
        state={'sources':{},'traffic':{'views':[{'timestamp':'2026-11-14T00:00:00Z','count':3,'uniques':2}]}}
        with patch.dict('os.environ',{'GH_METRICS_TOKEN':'test'}),patch.object(collect,'api',return_value={'views':[{'timestamp':'2026-11-14T00:00:00Z','count':7,'uniques':4}]}):
            collect.collect_traffic(state,{'repository':'owner/repo'},'views')
        self.assertEqual(len(state['traffic']['views']),1)
        self.assertEqual(state['traffic']['views'][0]['count'],7)

    def test_atom_feed_and_html_title_stay_plain_data(self):
        state={'mentions':{}}
        feed=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&lt;script&gt;bad&lt;/script&gt;</title><link href="https://example.com/post?utm_source=x"/></entry></feed>'
        with patch.object(collect,'request',return_value=feed):
            collect.collect_feed(state,{'name':'test','url':'https://example.com/feed'})
        self.assertIn('https://example.com/post',state['mentions'])
        self.assertEqual(state['mentions']['https://example.com/post']['title'],'<script>bad</script>')

if __name__=='__main__':
    unittest.main()
