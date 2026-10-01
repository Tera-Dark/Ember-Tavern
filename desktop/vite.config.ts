import {defineConfig} from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig({base:'./',plugins:[vue()],build:{outDir:'.vite/renderer',emptyOutDir:true},server:{host:'0.0.0.0',allowedHosts:true,proxy:{'/desktop-api':'http://127.0.0.1:8766'}}});
