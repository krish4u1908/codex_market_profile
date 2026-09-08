import { createRoot } from 'react-dom/client';
import { useState, useEffect } from 'react';
import MarketWorkspace from './components/market-workspace';
import { PROFILES } from './public/profiles.mjs';
import './app/globals.css';
import { loadWorkspaceConfig } from './public/workspace-config.mjs';

function App() {
  const [config,setConfig]=useState<any>(null),[error,setError]=useState('');
  const [profileId, setProfileId] = useState(() => {
    const id = new URLSearchParams(location.search).get('workspace');
    return id && id in PROFILES ? id : 'banknifty-v1062';
  });
  useEffect(()=>{let active=true;loadWorkspaceConfig().then(value=>{if(!active)return;const requested=new URLSearchParams(location.search).get('workspace');setConfig(value);setProfileId(requested&&value.profiles.includes(requested)?requested:value.defaultProfile);}).catch(error=>{if(active)setError(error.message);});return()=>{active=false;};},[]);
  const changeProfile = (id: string) => {
    if (!(id in PROFILES) || !config?.profiles.includes(id)) return;
    const url = new URL(location.href);
    url.searchParams.set('workspace', id);
    history.replaceState(null, '', url);
    setProfileId(id);
  };
  // Remount cancels both workers, pending fetches and summaries when switching.
  if(error)return <main className="welcome-card" role="alert"><h1>Workspace unavailable</h1><p>{error}</p><button onClick={()=>location.reload()}>Retry</button></main>;
  if(!config)return <main className="welcome-card" role="status">Opening market workspace…</main>;
  return <MarketWorkspace key={profileId} profileId={profileId} onProfileChange={changeProfile} workspaceConfig={config}/>;
}

createRoot(document.getElementById('root')!).render(<App/>);
