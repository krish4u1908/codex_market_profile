"""Read the existing minute feed and journal when Cash/VIX first became visible."""
import json
import os
from pathlib import Path
from .clock import parse_instant, iso_utc
from .cash_samples import build_sample_rows, _metadata_for_session


class LiveCashVixSource:
    def __init__(self,data_root,session,journal):
        self.root=Path(data_root); self.session=session; self.journal=Path(journal)
        self.rows=[]; self.seen=set(); self.signature=None; self.status='AWAITING_MINUTE_FEED'
        if self.journal.exists():
            for line in self.journal.read_text().splitlines():
                row=json.loads(line); self.rows.append(row); self.seen.add(row['minute_ist'])

    def poll(self,as_of):
        as_of=parse_instant(as_of)
        source=self.root/'minute'/self.session.isoformat()/'market_1m.csv'
        try:
            stat=source.stat(); signature=(stat.st_size,stat.st_mtime_ns,as_of.replace(second=0,microsecond=0))
            if signature==self.signature: return self.rows
            with source.open('rb') as handle:
                if stat.st_size:
                    handle.seek(-1,2)
                    if handle.read(1)!=b'\n':
                        self.status='MINUTE_WRITE_IN_PROGRESS'; return self.rows
            metadata=_metadata_for_session(self.root,self.session)
            samples,_=build_sample_rows(source,self.session,metadata=None if metadata is None else metadata['row'])
            after=source.stat()
            if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):
                self.status='MINUTE_WRITE_IN_PROGRESS'; return self.rows
            added=[]
            for sample in samples:
                if sample['minute_ist'] in self.seen or parse_instant(sample['t'])>as_of: continue
                # Preserve both clocks. Late startup data cannot appear in past calls.
                row={**sample,'source_published_at':sample['t'],'t':iso_utc(as_of),'first_observed_at':iso_utc(as_of)}
                self.seen.add(row['minute_ist']); added.append(row)
            if added:
                self.journal.parent.mkdir(parents=True,exist_ok=True)
                with self.journal.open('a') as handle:
                    for row in added: handle.write(json.dumps(row,sort_keys=True)+'\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                self.rows.extend(added)
            self.signature=signature; self.status='AVAILABLE' if self.rows else 'AWAITING_COMPLETED_CASH_MINUTE'
        except (OSError,ValueError,KeyError) as error:
            self.status='CASH_FEED_UNAVAILABLE: '+str(error)
        return self.rows
