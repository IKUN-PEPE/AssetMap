import { createRouter, createWebHistory } from 'vue-router'

const AdminLayout = () => import('@/layouts/AdminLayout.vue')
const DashboardView = () => import('@/views/DashboardView.vue')
const JobsView = () => import('@/views/JobsView.vue')
const AssetsView = () => import('@/views/AssetsView.vue')
const AssetDetailView = () => import('@/views/AssetDetailView.vue')
const SelectionsView = () => import('@/views/SelectionsView.vue')
const ReportsView = () => import('@/views/ReportsView.vue')
const SystemView = () => import('@/views/SystemView.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: AdminLayout,
      children: [
        { path: '', name: 'dashboard', component: DashboardView },
        { path: 'jobs', name: 'jobs', component: JobsView },
        { path: 'assets', name: 'assets', component: AssetsView },
        { path: 'assets/:id', name: 'asset-detail', component: AssetDetailView, props: true },
        { path: 'selections', name: 'selections', component: SelectionsView },
        { path: 'reports', name: 'reports', component: ReportsView },
        { path: 'system', name: 'system', component: SystemView },
      ],
    },
  ],
})

export default router
