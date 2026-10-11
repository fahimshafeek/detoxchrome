<script lang="ts">
  import { onMount } from 'svelte';
  import { Command } from '@tauri-apps/plugin-shell';
  import { Switch } from '$lib/components/ui/switch';
  import { Card } from '$lib/components/ui/card';
  import { Button } from '$lib/components/ui/button';
  import { Checkbox } from '$lib/components/ui/checkbox';
  import { toast } from 'svelte-sonner';
  import { mode, setMode } from 'mode-watcher';
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  import Search from '@lucide/svelte/icons/search';
  import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
  import X from '@lucide/svelte/icons/x';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import CircleX from '@lucide/svelte/icons/circle-x';
  import Trash from '@lucide/svelte/icons/trash';
  import Download from '@lucide/svelte/icons/download';
  import Zap from '@lucide/svelte/icons/zap';
  import * as AlertDialog from '$lib/components/ui/alert-dialog';

  interface AppItem {
    id: string;
    name: string;
    category: string;
    enabled: boolean;
    selected: boolean;
  }

  let masterEnabled = $state(false);
  let isDarkMode = $derived(mode.current === 'dark');
  let device = $state<{serial: string, name: string, brand: string, model: string} | null>(null);
  let apps = $state<AppItem[]>([]);
  let debloating = $state(false);
  let installingApk = $state(false);
  let oneClickProcessing = $state(false);
  let checkingDevice = $state(false);
  let confirmAction = $state<'debloat' | 'one-click' | null>(null);
  let restoringAppId = $state<string | null>(null);

  // Search & Categories
  let searchQuery = $state('');
  let selectedCategory = $state('All');

  const CATEGORIES = ['All', 'Social', 'Media', 'Browsers', 'Games', 'Productivity', 'System'];

  const STORAGE_KEY_DEBLOATED_DEVICES = 'debloater_enabled_devices';

  function getRememberedDevices(): string[] {
    try {
      const data = localStorage.getItem(STORAGE_KEY_DEBLOATED_DEVICES);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  function rememberDevice(serial: string) {
    try {
      const list = getRememberedDevices();
      if (!list.includes(serial)) {
        list.push(serial);
        localStorage.setItem(STORAGE_KEY_DEBLOATED_DEVICES, JSON.stringify(list));
      }
    } catch {}
  }

  function forgetDevice(serial: string) {
    try {
      let list = getRememberedDevices();
      list = list.filter(s => s !== serial);
      localStorage.setItem(STORAGE_KEY_DEBLOATED_DEVICES, JSON.stringify(list));
    } catch {}
  }

  async function checkConnectedDevice() {
    if (checkingDevice) return;
    checkingDevice = true;
    try {
      const command = Command.sidecar("backend", ["device"]);
      const output = await command.execute();
      if (output.code === 0) {
        const result = JSON.parse(output.stdout);
        if (result && result.serial) {
          device = result;
          const remembered = getRememberedDevices();
          if (remembered.includes(result.serial) && !masterEnabled) {
            masterEnabled = true;
            loadStatus();
          }
        }
      }
    } catch (e) {
    } finally {
      checkingDevice = false;
    }
  }

  async function loadStatus() {
    try {
      const command = Command.sidecar("backend", ["status"]);
      const output = await command.execute();
      
      if (output.code === 0) {
        const result = JSON.parse(output.stdout);
        if (result.error) {
          toast.error(result.error);
        } else {
          if (result.device) {
            device = result.device;
            rememberDevice(result.device.serial);
          }
          apps = result.apps.map((a: any) => ({
            ...a, 
            category: a.category || 'Other',
            selected: true
          }));
        }
      } else {
        toast.error("Failed to run backend: " + output.stderr);
      }
    } catch (e: any) {
      toast.error("Error connecting to sidecar: " + e.message);
    }
  }

  function handleMasterToggle(checked: boolean) {
    masterEnabled = checked;
    if (checked) {
      loadStatus();
    } else {
      if (device?.serial) {
        forgetDevice(device.serial);
      }
    }
  }

  function requestDebloatConfirmation() {
    const selectedApps = apps.filter(a => a.selected && a.enabled);
    if (selectedApps.length === 0) {
      toast.info("No active apps selected for debloating.");
      return;
    }
    confirmAction = 'debloat';
  }

  function requestOneClickConfirmation() {
    confirmAction = 'one-click';
  }

  async function executeDebloat() {
    confirmAction = null;
    const selectedApps = apps.filter(a => a.selected && a.enabled);
    if (selectedApps.length === 0) return;

    debloating = true;
    let successCount = 0;

    for (const app of selectedApps) {
      try {
        const command = Command.sidecar("backend", ["toggle", app.id, "0"]);
        const output = await command.execute();
        if (output.code === 0) {
          const result = JSON.parse(output.stdout);
          if (result.success) {
            app.enabled = false;
            app.selected = false;
            successCount++;
          }
        }
      } catch (e) {
      }
    }

    debloating = false;
    if (successCount === selectedApps.length) {
      toast.success(`Successfully debloated ${successCount} apps!`);
    } else {
      toast.warning(`Debloated ${successCount} out of ${selectedApps.length} selected apps.`);
    }
  }

  async function executeInstallApk(): Promise<boolean> {
    installingApk = true;
    toast.info("Installing Detox Chromium APK onto your phone...");
    try {
      const command = Command.sidecar("backend", ["install_apk"]);
      const output = await command.execute();
      if (output.code === 0) {
        const result = JSON.parse(output.stdout);
        if (result.success) {
          toast.success(result.message || "Detox Chromium APK installed successfully!");
          await loadStatus();
          return true;
        } else {
          toast.error(`APK install failed: ${result.error}`);
          return false;
        }
      } else {
        toast.error(`Install error: ${output.stderr}`);
        return false;
      }
    } catch (e: any) {
      toast.error(`Failed to install APK: ${e.message}`);
      return false;
    } finally {
      installingApk = false;
    }
  }

  async function executeOneClickDetox() {
    confirmAction = null;
    oneClickProcessing = true;

    // 1. Debloat all active selected apps
    const selectedApps = apps.filter(a => a.selected && a.enabled);
    let debloatedCount = 0;
    for (const app of selectedApps) {
      try {
        const command = Command.sidecar("backend", ["toggle", app.id, "0"]);
        const output = await command.execute();
        if (output.code === 0) {
          const result = JSON.parse(output.stdout);
          if (result.success) {
            app.enabled = false;
            app.selected = false;
            debloatedCount++;
          }
        }
      } catch (e) {}
    }

    // 2. Install Detox Chromium APK
    toast.info(`Debloated ${debloatedCount} apps. Now installing Detox Chromium APK...`);
    const apkSuccess = await executeInstallApk();

    oneClickProcessing = false;
    if (apkSuccess) {
      toast.success(`Detox complete! Debloated ${debloatedCount} apps & installed Detox Chromium.`);
    } else {
      toast.warning(`Debloated ${debloatedCount} apps, but APK installation encountered an error.`);
    }
  }

  async function restoreApp(app: AppItem) {
    restoringAppId = app.id;
    try {
      const command = Command.sidecar("backend", ["toggle", app.id, "1"]);
      const output = await command.execute();
      if (output.code === 0) {
        const result = JSON.parse(output.stdout);
        if (result.success) {
          app.enabled = true;
          app.selected = true;
          toast.success(`Restored ${app.name}!`);
        } else {
          toast.error(`Failed to restore ${app.name}: ${result.error || 'Unknown error'}`);
        }
      } else {
        toast.error(`Error restoring ${app.name}`);
      }
    } catch (e: any) {
      toast.error(`Restore error: ${e.message}`);
    } finally {
      restoringAppId = null;
    }
  }

  let filteredApps = $derived(
    apps.filter(app => {
      const query = searchQuery.trim().toLowerCase();
      const matchesSearch = query === '' || 
        app.name.toLowerCase().includes(query) || 
        app.id.toLowerCase().includes(query);
      const matchesCategory = selectedCategory === 'All' || app.category === selectedCategory;
      return matchesSearch && matchesCategory;
    })
  );

  let categoryCounts = $derived(
    CATEGORIES.reduce((acc, cat) => {
      acc[cat] = cat === 'All' ? apps.length : apps.filter(a => a.category === cat).length;
      return acc;
    }, {} as Record<string, number>)
  );

  let activeFilteredApps = $derived(filteredApps.filter(a => a.enabled));
  let allSelected = $derived(activeFilteredApps.length > 0 && activeFilteredApps.every(a => a.selected));
  let someSelected = $derived(activeFilteredApps.some(a => a.selected));

  function selectAll() {
    for (const app of filteredApps) {
      if (app.enabled) {
        app.selected = true;
      }
    }
  }

  function deselectAll() {
    for (const app of filteredApps) {
      if (app.enabled) {
        app.selected = false;
      }
    }
  }

  onMount(() => {
    checkConnectedDevice();
    const interval = setInterval(() => {
      if (!masterEnabled) {
        checkConnectedDevice();
      }
    }, 3000);
    return () => clearInterval(interval);
  });
</script>

<main class="min-h-screen w-full flex flex-col items-center bg-background overflow-y-auto overflow-x-hidden relative">
  <!-- Theme changing button in the top right corner -->
  <div class="fixed top-6 right-6 z-50">
    <button 
      type="button"
      class="flex items-center space-x-2 px-3 py-1.5 rounded-full border border-border bg-card text-card-foreground shadow-sm hover:bg-muted transition-colors cursor-pointer"
      onclick={() => setMode(isDarkMode ? 'light' : 'dark')}
      aria-label="Toggle color theme"
    >
      {#if isDarkMode}
        <Sun class="h-4 w-4 text-amber-400" />
        <span class="text-xs font-medium">Light</span>
      {:else}
        <Moon class="h-4 w-4 text-slate-700" />
        <span class="text-xs font-medium">Dark</span>
      {/if}
    </button>
  </div>

  <!-- Header & Master Toggle: Centered initially at 38vh, scrolls naturally with the page -->
  <div class="w-full flex flex-col items-center justify-center shrink-0 pt-[38vh] pb-4">
    <div class="flex flex-col items-center justify-center space-y-4">
      <div class="h-4 flex items-center justify-center">
        {#if masterEnabled && device}
          <span class="text-xs font-medium tracking-wide uppercase text-muted-foreground">{device.name}</span>
        {/if}
      </div>

      <div class="flex items-center justify-center w-12 h-8">
        <Switch checked={masterEnabled} onCheckedChange={handleMasterToggle} class="scale-150 origin-center" />
      </div>

      {#if masterEnabled && apps.length > 0}
        <div class="flex flex-wrap items-center justify-center gap-3 mt-3 px-4">
          <!-- Button 1: Debloat Selected -->
          <Button 
            disabled={debloating || installingApk || oneClickProcessing} 
            onclick={requestDebloatConfirmation} 
            size="default" 
            variant="destructive"
            class="shadow-sm cursor-pointer flex items-center space-x-1.5"
          >
            <Trash class="h-4 w-4" />
            <span>{debloating ? 'Debloating...' : 'Debloat Selected'}</span>
          </Button>

          <!-- Button 2: Install APK Only -->
          <Button 
            disabled={debloating || installingApk || oneClickProcessing} 
            onclick={executeInstallApk} 
            size="default" 
            variant="secondary"
            class="shadow-sm cursor-pointer flex items-center space-x-1.5 border border-border"
          >
            <Download class="h-4 w-4 {installingApk ? 'animate-bounce' : ''}" />
            <span>{installingApk ? 'Installing APK...' : 'Install Detox APK'}</span>
          </Button>

          <!-- Button 3: Debloat & Install on One Click -->
          <Button 
            disabled={debloating || installingApk || oneClickProcessing} 
            onclick={requestOneClickConfirmation} 
            size="default" 
            class="shadow-sm cursor-pointer flex items-center space-x-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Zap class="h-4 w-4 {oneClickProcessing ? 'animate-pulse' : ''}" />
            <span>{oneClickProcessing ? 'Detoxing Phone...' : 'Debloat & Install APK'}</span>
          </Button>
        </div>
      {/if}
    </div>
  </div>

  <!-- Search & Category Filter Section -->
  {#if masterEnabled && apps.length > 0}
    <div class="w-full max-w-4xl px-6 mt-6 flex flex-col items-center space-y-4">
      <!-- Search Bar -->
      <div class="relative w-full max-w-md flex items-center">
        <Search class="absolute left-3.5 h-4 w-4 text-muted-foreground pointer-events-none" />
        <input 
          type="text"
          placeholder="Search apps by name or package..."
          bind:value={searchQuery}
          class="w-full pl-10 pr-9 py-2 text-sm rounded-full border border-border bg-card text-card-foreground shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {#if searchQuery.length > 0}
          <button 
            type="button" 
            onclick={() => searchQuery = ''}
            class="absolute right-3 p-0.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            aria-label="Clear search"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        {/if}
      </div>

      <!-- Category Filter Chips -->
      <div class="flex flex-wrap items-center justify-center gap-2">
        {#each CATEGORIES as category}
          <button
            type="button"
            onclick={() => selectedCategory = category}
            class="flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer border {selectedCategory === category ? 'bg-primary text-primary-foreground border-primary' : 'bg-card text-muted-foreground hover:text-foreground border-border hover:bg-muted'}"
          >
            <span>{category}</span>
            <span class="text-[10px] opacity-75 font-mono">({categoryCounts[category] || 0})</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Apps Cards Area: with small gap from debloat button / filters above -->
  {#if masterEnabled}
    <div class="w-full max-w-4xl px-6 pb-24 mt-6">
      {#if apps.length === 0}
        <div class="flex flex-col items-center justify-center py-16 space-y-3">
          <div class="text-muted-foreground text-sm">
            {device ? 'Loading packages from phone...' : 'No device connected. Please connect via USB.'}
          </div>
          <Button variant="outline" size="sm" onclick={loadStatus}>
            Retry
          </Button>
        </div>
      {:else if filteredApps.length === 0}
        <div class="flex flex-col items-center justify-center py-16 space-y-2 text-center">
          <p class="text-sm font-medium text-foreground">No matching apps found</p>
          <p class="text-xs text-muted-foreground">Try adjusting your search query or selected category.</p>
          <Button variant="outline" size="sm" class="mt-2" onclick={() => { searchQuery = ''; selectedCategory = 'All'; }}>
            Reset Filters
          </Button>
        </div>
      {:else}
        <!-- Selection toolbar -->
        <div class="flex items-center justify-between w-full mb-3 px-1">
          <span class="text-xs text-muted-foreground">
            {activeFilteredApps.filter(a => a.selected).length} of {activeFilteredApps.length} active apps selected
          </span>
          <div class="flex items-center space-x-2">
            {#if someSelected}
              <Button 
                variant="ghost" 
                size="sm" 
                class="h-7 text-xs text-muted-foreground hover:text-foreground cursor-pointer px-2"
                onclick={deselectAll}
              >
                Deselect All
              </Button>
            {/if}
            {#if !allSelected}
              <Button 
                variant="ghost" 
                size="sm" 
                class="h-7 text-xs text-muted-foreground hover:text-foreground cursor-pointer px-2"
                onclick={selectAll}
              >
                Select All
              </Button>
            {/if}
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {#each filteredApps as app (app.id)}
            <Card class="flex items-start justify-between p-5 hover:bg-muted/50 transition-colors">
              <div class="flex flex-col space-y-1.5 overflow-hidden pr-2 flex-1">
                <div class="flex items-center space-x-2">
                  <span class="text-sm font-semibold tracking-tight truncate">{app.name}</span>
                  <span class="text-[10px] px-2 py-0.5 rounded-full bg-muted font-medium text-muted-foreground shrink-0">
                    {app.category}
                  </span>
                </div>
                <span class="text-xs text-muted-foreground break-all">{app.id}</span>
                <div class="flex items-center pt-1">
                  {#if app.enabled}
                    <div class="flex items-center text-foreground/70" title="Installed">
                      <CircleCheck class="h-4 w-4" />
                    </div>
                  {:else}
                    <div class="flex items-center text-muted-foreground/40" title="Uninstalled">
                      <CircleX class="h-4 w-4" />
                    </div>
                  {/if}
                </div>
              </div>

              <div class="flex items-center ml-2 shrink-0">
                {#if app.enabled}
                  <Checkbox 
                    id="check-{app.id}" 
                    bind:checked={app.selected} 
                  />
                {:else}
                  <Button 
                    size="sm" 
                    variant="outline" 
                    class="h-8 px-2.5 text-xs flex items-center space-x-1 border-primary/40 hover:bg-primary hover:text-primary-foreground transition-colors cursor-pointer"
                    disabled={restoringAppId === app.id}
                    onclick={() => restoreApp(app)}
                  >
                    <RotateCcw class="h-3 w-3 {restoringAppId === app.id ? 'animate-spin' : ''}" />
                    <span>{restoringAppId === app.id ? 'Restoring...' : 'Restore'}</span>
                  </Button>
                {/if}
              </div>
            </Card>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Confirmation Modal -->
  <AlertDialog.Root open={confirmAction !== null} onOpenChange={(open) => { if (!open) confirmAction = null; }}>
    <AlertDialog.Content>
      <AlertDialog.Header>
        <AlertDialog.Title>
          {confirmAction === 'one-click' ? 'Confirm One-Click Detox' : 'Confirm Debloat'}
        </AlertDialog.Title>
        <AlertDialog.Description>
          {#if confirmAction === 'one-click'}
            This will uninstall {apps.filter(a => a.selected && a.enabled).length} selected apps and install the Detox Chromium APK on {device?.name || 'your device'} in one click.
          {:else}
            Are you sure you want to uninstall {apps.filter(a => a.selected && a.enabled).length} selected package(s) from {device?.name || 'your device'}? This will disable them for user 0.
          {/if}
        </AlertDialog.Description>
      </AlertDialog.Header>
      <AlertDialog.Footer>
        <AlertDialog.Cancel onclick={() => confirmAction = null}>Cancel</AlertDialog.Cancel>
        <AlertDialog.Action onclick={() => {
          if (confirmAction === 'one-click') {
            executeOneClickDetox();
          } else {
            executeDebloat();
          }
        }}>
          Confirm
        </AlertDialog.Action>
      </AlertDialog.Footer>
    </AlertDialog.Content>
  </AlertDialog.Root>
</main>
