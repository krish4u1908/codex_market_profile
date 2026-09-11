from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import pwd
import grp
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deploy import install as installer
from market_core.migration import sha256
from tests.test_migration import old_state


class InstallerTests(unittest.TestCase):
    def test_scope_guards_and_gui_has_no_engine_dependency(self):
        cfg=installer.read_deployment()
        rows=json.loads((installer.CORE/'deploy/old-units.json').read_text())
        protected={'nifty-collector.service','fyers-auth.service','fyers-bot.service','banknifty-new-divergence-codex.service','cron.service','user@1002.service'}
        self.assertFalse(protected & {row['name'] for row in rows})
        self.assertTrue(all(row['scope']=='user:codexuser' for row in rows if row['name'].startswith('nifty-')))
        for instrument in cfg['instruments']:
            core=installer.unit_text(cfg,instrument,'core');gui=installer.unit_text(cfg,instrument,'gui')
            self.assertIn('-m market_core.server',core)
            self.assertIn('-m market_core.gui',gui)
            self.assertNotIn('Requires=',gui);self.assertNotIn('PartOf=',gui)
            self.assertNotIn('SupplementaryGroups=',gui)
            self.assertIn('ProtectSystem=strict',core)
        self.assertTrue(installer.retired_problem({'ActiveState':'active','UnitFileState':'disabled'}))
        self.assertTrue(installer.retired_problem({'ActiveState':'inactive','UnitFileState':'enabled'}))
        self.assertFalse(installer.retired_problem({'ActiveState':'inactive','UnitFileState':'disabled'}))

    def setup_bundle(self,root):
        bundle=root/'bundle';(bundle/'core').mkdir(parents=True);(bundle/'gui').mkdir()
        (bundle/'gui/index.html').write_text('built UI')
        (bundle/'core/requirements.txt').write_text('numpy==2.3.5\npandas==2.2.3\n')
        manifest={'files':[{'path':str(p.relative_to(bundle)),'sha256':sha256(p)} for p in bundle.rglob('*') if p.is_file()]}
        (bundle/'BUNDLE-MANIFEST.json').write_text(json.dumps(manifest))
        cfg=installer.read_deployment();cfg.update(expected_host=socket.gethostname(),
            service_user=pwd.getpwuid(os.getuid()).pw_name,service_group=grp.getgrgid(os.getgid()).gr_name,
            collector_group=grp.getgrgid(os.getgid()).gr_name,install_root=str(root/'install'),state_root=str(root/'state'))
        for instrument,item in cfg['instruments'].items():
            old=root/('old-'+instrument);old_state(old,instrument)
            collector=root/('collector-'+instrument);collector.mkdir()
            item.update(old_state=str(old),collector_root=str(collector),prior=None,prepared={})
        return bundle,cfg

    def test_first_install_and_rollback_only_mutate_four_new_units(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root=Path(tmp);bundle,cfg=self.setup_bundle(root)
            units=root/'units';units.mkdir();calls=[]
            def run(argv,**kwargs):
                calls.append(list(map(str,argv)));return SimpleNamespace(returncode=0,stdout='',stderr='')
            for name,value in [('UNIT_ROOT',units),('old_state_report',lambda:[]),('occupied_ports',lambda:set()),('leftover_processes',lambda:[]),('run',run)]:
                stack.enter_context(patch.object(installer,name,value))
            stack.enter_context(patch('deploy.install.os.geteuid',return_value=0))
            stack.enter_context(patch('deploy.install.os.chown'))
            status={'units':{u:{'ActiveState':'active'} for u in installer.UNITS},'endpoints':{i+' '+role:{'instrument':i,'status':'waiting'} for i in cfg['instruments'] for role in ('core','gui')}}
            stack.enter_context(patch.object(installer,'status',return_value=status))
            stack.enter_context(redirect_stdout(io.StringIO()))
            before={p:sha256(p) for i in cfg['instruments'].values() for p in Path(i['old_state']).rglob('*') if p.is_file()}
            installer.install(cfg,bundle,None)
            for p,digest in before.items(): self.assertEqual(sha256(p),digest)
            record=next((root/'install/install-records').glob('*.json'))
            self.assertEqual(json.loads(record.read_text())['phase'],'installed')
            self.assertEqual({p.name for p in units.iterdir()},set(installer.UNITS))
            config=(root/'install/current/config/banknifty.json')
            self.assertTrue(config.stat().st_mode & 0o004)
            installer.rollback(cfg,record)
            mutated={call[-1] for call in calls if call[:2] in (['systemctl','enable'],['systemctl','disable'])}
            self.assertEqual(mutated,set(installer.UNITS))
            self.assertTrue((root/'state/banknifty/runtime/context.sqlite3').is_file())
            self.assertEqual(json.loads(record.read_text())['phase'],'rolled-back')

    def test_active_legacy_engine_blocks_before_install_writes(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root=Path(tmp);bundle,cfg=self.setup_bundle(root)
            stack.enter_context(patch.object(installer,'UNIT_ROOT',root/'units'))
            stack.enter_context(patch.object(installer,'old_state_report',return_value=[{'scope':'user:codexuser','name':'nifty-v200-live.service','problem':'still active'}]))
            stack.enter_context(patch.object(installer,'occupied_ports',return_value={8913}))
            stack.enter_context(patch.object(installer,'leftover_processes',return_value=[]))
            stack.enter_context(patch.object(installer,'run',return_value=SimpleNamespace(returncode=0)))
            stack.enter_context(redirect_stdout(io.StringIO()))
            with self.assertRaisesRegex(RuntimeError,'Preflight failed'): installer.install(cfg,bundle,None)
            self.assertFalse((root/'install').exists());self.assertFalse((root/'state').exists())


if __name__=='__main__': unittest.main(verbosity=2)
