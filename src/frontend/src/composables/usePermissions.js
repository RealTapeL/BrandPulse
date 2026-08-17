import { computed } from 'vue'
import { useUserStore } from '../stores/user'

/** 仅用于界面呈现；所有真实授权仍由后端 RBAC 决定。 */
export function usePermissions() {
  const userStore = useUserStore()
  const can = (permission) => computed(() => userStore.hasPermission(permission))
  return { userStore, can }
}
