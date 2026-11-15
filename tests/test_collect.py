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

class DuckDuckGoTests(unittest.TestCase):
    def test_parses_nested_titles_and_redirects(self):
        html = '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reddit.com%2Fr%2F3ds%2Fcomments%2Fabc123%2Ftitle%2F">3DSRP <b>release</b> &amp; news</a>'
        self.assertEqual(collect.parse_duckduckgo(html), [{"url":"https://reddit.com/comments/abc123", "title":"3DSRP release & news"}])

    def test_challenge_and_changed_markup_are_not_zero_results(self):
        with self.assertRaises(collect.DuckDuckGoBlocked):
            collect.parse_duckduckgo('<form id="challenge-form" action="anomaly.js">')
        with self.assertRaises(collect.DuckDuckGoMarkupChanged):
            collect.parse_duckduckgo('<html>Unexpected service error</html>')
        self.assertEqual(collect.parse_duckduckgo('<div class="no-results">No results found</div>'), [])

    def test_partial_search_preserves_api_metrics_and_records_failure(self):
        url='https://reddit.com/comments/abc123'
        state={'mentions':{url:{'url':url,'title':'API title','metrics':{'score':12},'updated_at':'yesterday','discovery':'Reddit API'}},'sources':{}}
        first='<a class="result__a" href="https://reddit.com/comments/abc123">Search title</a><a class="result__a" href="https://example.com/news">New coverage</a>'
        with patch.object(collect,'request',side_effect=[first.encode(),b'<form id="challenge-form">']),patch.object(collect.time,'sleep'):
            collect.collect_duckduckgo(state,{'duckduckgo_queries':['first','second','third']})
        self.assertEqual(state['mentions'][url]['title'],'API title')
        self.assertEqual(state['mentions'][url]['metrics']['score'],12)
        self.assertEqual(state['mentions'][url]['updated_at'],'yesterday')
        self.assertIn('https://example.com/news',state['mentions'])
        self.assertEqual(state['sources']['DuckDuckGo']['status'],'partial')
        self.assertIn('1/3',state['sources']['DuckDuckGo']['message'])

    def test_platform_matching_and_video_deduplication(self):
        self.assertEqual(collect.platform_for('https://notreddit.com/post'),'Web')
        self.assertEqual(collect.platform_for('https://old.reddit.com/post'),'Reddit')
        self.assertEqual(collect.canonical('https://youtu.be/abcdefghijk?si=tracking'),collect.canonical('https://www.youtube.com/watch?v=abcdefghijk&feature=share'))

    def test_success_and_empty_results(self):
        state={'mentions':{},'sources':{}}
        with patch.object(collect,'request',return_value=b'<div class="no-results">No results found</div>'):
            collect.collect_duckduckgo(state,{'duckduckgo_queries':['3DSRP']})
        self.assertEqual(state['sources']['DuckDuckGo']['status'],'ok')
        self.assertEqual(state['mentions'],{})

if __name__=='__main__':
    unittest.main()
