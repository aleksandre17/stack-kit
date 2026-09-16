import { defineConfig } from 'vite'
// env from ops/config/web (test_vite_env_dir_points_to_ops_config)
export default defineConfig({ envDir: '../../ops/config/web' })
