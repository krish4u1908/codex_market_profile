import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import MarketWorkspace from './components/market-workspace';
import { PROFILES } from './public/profiles.mjs';
import './app/globals.css';

function App() {
  const [profileId, setProfileId] = useState(() => {
    const id = new URLSearchParams(location.search).get('workspace');
    return id && id in PROFILES ? id : 'banknifty-v1062';
  });
  const changeProfile = (id: string) => {
    if (!(id in PROFILES)) return;
    const url = new URL(location.href);
    url.searchParams.set('workspace', id);
    history.replaceState(null, '', url);
    setProfileId(id);
  };
  // Remount cancels both workers, pending fetches and summaries when switching.
  return <MarketWorkspace key={profileId} profileId={profileId} onProfileChange={changeProfile}/>;
}

createRoot(document.getElementById('root')!).render(<App/>);
