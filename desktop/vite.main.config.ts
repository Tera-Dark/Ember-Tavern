import {defineConfig} from 'vite';
import {builtinModules} from 'node:module';
export default defineConfig({build:{outDir:'.vite',emptyOutDir:false,minify:false,lib:{entry:{main:'src/main/main.ts',preload:'src/main/preload.ts','game-preload':'src/main/game-preload.ts',core:'src/main/core.ts','ipc-payload':'src/ipc-payload.ts'},formats:['cjs'],fileName:(_,name)=>name+'.cjs'},rollupOptions:{external:['electron',...builtinModules,...builtinModules.map(name=>'node:'+name)]}}});
