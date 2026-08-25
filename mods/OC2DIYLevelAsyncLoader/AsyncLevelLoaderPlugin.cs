using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using BepInEx;
using BepInEx.Configuration;
using HarmonyLib;
using LevelEditorStub;
using OC2DIYLevel;
using OC2DIYLevel.CustomArcade;
using UnityEngine;

namespace OC2DIYLevelAsyncLoader
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    [BepInDependency(DiyLevelPluginGuid, BepInDependency.DependencyFlags.HardDependency)]
    [BepInProcess("Overcooked2.exe")]
    public sealed class AsyncLevelLoaderPlugin : BaseUnityPlugin
    {
        public const string PluginGuid = "dukey.oc2.diylevel.asyncloader";
        public const string PluginName = "OC2 DIY Level Async Loader by DUKEY";
        public const string PluginVersion = "0.1.0";
        public const string DiyLevelPluginGuid = "dev.gua.overcooked.diylevel";

        private const string SupportedDiyLevelSha256 = "18387FF6923281198518D67EDDA3B8E728A4E5AA7407104E03A1F0AC82811D06";
        private static readonly Guid SupportedDiyLevelMvid = new Guid("30222f4f-5818-4195-9678-8e07f0b4ee76");

        private enum LoaderState
        {
            Disabled,
            Idle,
            Loading,
            Ready,
            Failed
        }

        private sealed class LevelBundleCandidate
        {
            public DirectoryInfo Directory;
            public FileInfo InfoFile;
        }

        private static AsyncLevelLoaderPlugin pluginInstance;
        private static bool allowOriginalInitializeOnce;

        private Harmony harmony;
        private bool interceptEnabled;
        private bool originalInitializeRequested;
        private LoaderState state = LoaderState.Disabled;

        private ConfigEntry<bool> preloadOnStartup;
        private ConfigEntry<bool> showProgress;
        private ConfigEntry<bool> skipDuplicateInfoNames;
        private ConfigEntry<bool> fallbackToSynchronous;

        private MethodInfo initializeMethod;
        private MethodInfo refreshDlcButtonsMethod;
        private MethodInfo customArcadeAddUiMethod;
        private FieldInfo managerInstanceField;
        private FieldInfo commonBundleField;
        private FieldInfo diyLevelCoverField;
        private FieldInfo diyLevelGameSessionPrefabField;
        private FieldInfo configTemplateSoField;

        private FrontendDLCMenu lastDlcMenu;
        private readonly List<AssetBundle> retainedBundles = new List<AssetBundle>();
        private List<AssetBundle> activeLoadedBundles;
        private Coroutine activeInitializationCoroutine;
        private Coroutine fallbackCoroutine;
        private bool fallbackScheduled;
        private AsyncOperation currentOperation;
        private float operationBase;
        private float operationWeight;
        private int completedItems;
        private int totalItems;
        private int loadedLevelSets;
        private int skippedDuplicateBundles;
        private int missingInfoDirectories;
        private int failedLevelBundles;
        private string currentStatus = string.Empty;
        private string lastError = string.Empty;
        private float readyMessageUntil;
        private GUIStyle titleStyle;
        private GUIStyle detailStyle;
        private GUIStyle centerStyle;

        private void Awake()
        {
            pluginInstance = this;

            preloadOnStartup = Config.Bind(
                "Loading",
                "PreloadOnStartup",
                true,
                "Begin asynchronous loading on the title screen. If disabled, loading starts when OC2DIYLevel calls Initialize().");
            showProgress = Config.Bind(
                "Display",
                "ShowProgress",
                true,
                "Show a small non-interactive progress panel while custom levels are loading.");
            skipDuplicateInfoNames = Config.Bind(
                "Loading",
                "SkipDuplicateInfoNames",
                false,
                "After the first info bundle with a given file name loads successfully, skip later same-name conflicts. Enable only when logs confirm those names collide.");
            fallbackToSynchronous = Config.Bind(
                "Compatibility",
                "FallbackToSynchronous",
                true,
                "If fatal asynchronous initialization fails, allow OC2DIYLevel's original synchronous initializer to run.");

            if (!ValidateSupportedInstallation())
            {
                state = LoaderState.Disabled;
                Logger.LogWarning("Compatibility checks failed. The async loader is disabled and OC2DIYLevel will keep its original synchronous behaviour.");
                return;
            }

            MethodInfo initializePrefix = AccessTools.Method(typeof(AsyncLevelLoaderPlugin), "OriginalInitializePrefix");
            MethodInfo refreshPostfix = AccessTools.Method(typeof(AsyncLevelLoaderPlugin), "RefreshDlcButtonsPostfix");
            MethodInfo customArcadePrefix = AccessTools.Method(typeof(AsyncLevelLoaderPlugin), "CustomArcadeAddUiPrefix");

            harmony = new Harmony(PluginGuid);
            harmony.Patch(initializeMethod, new HarmonyMethod(initializePrefix), null);
            harmony.Patch(refreshDlcButtonsMethod, null, new HarmonyMethod(refreshPostfix));
            harmony.Patch(customArcadeAddUiMethod, new HarmonyMethod(customArcadePrefix), null);

            interceptEnabled = true;
            state = LoaderState.Idle;
            DIYLevelAssetBundleManager.levelSetInfos = new List<KeyValuePair<string, LevelSetInfoSO>>();
            Logger.LogInfo("Compatibility checks passed for OC2DIYLevel 0.9.0. Original synchronous Initialize() is intercepted.");
        }

        private void Start()
        {
            if (interceptEnabled && preloadOnStartup.Value)
            {
                StartCoroutine(BeginPreloadNextFrame());
            }
        }

        private void Update()
        {
            if (interceptEnabled && state == LoaderState.Failed && DIYLevelAssetBundleManager.IsInitialized)
            {
                state = LoaderState.Ready;
                currentStatus = "OC2DIYLevel original synchronous fallback completed.";
                readyMessageUntil = Time.realtimeSinceStartup + 5f;
                StartCoroutine(RefreshMenusWhenAvailable());
            }
        }

        private void OnDestroy()
        {
            if (activeInitializationCoroutine != null)
            {
                StopCoroutine(activeInitializationCoroutine);
                activeInitializationCoroutine = null;
            }
            if (fallbackCoroutine != null)
            {
                StopCoroutine(fallbackCoroutine);
                fallbackCoroutine = null;
            }
            fallbackScheduled = false;

            if (activeLoadedBundles != null)
            {
                for (int index = activeLoadedBundles.Count - 1; index >= 0; index--)
                {
                    SafeUnloadBundle(activeLoadedBundles[index], true);
                }
                activeLoadedBundles.Clear();
                activeLoadedBundles = null;
            }

            if (harmony != null)
            {
                harmony.UnpatchAll(PluginGuid);
            }

            if (pluginInstance == this)
            {
                pluginInstance = null;
            }
        }

        private IEnumerator BeginPreloadNextFrame()
        {
            yield return null;
            BeginAsyncInitialization("title-screen preload");
        }

        private static bool OriginalInitializePrefix()
        {
            AsyncLevelLoaderPlugin plugin = pluginInstance;
            if (plugin == null || !plugin.interceptEnabled)
            {
                return true;
            }

            if (allowOriginalInitializeOnce)
            {
                allowOriginalInitializeOnce = false;
                plugin.Logger.LogWarning("Allowing OC2DIYLevel's original synchronous Initialize() as a fallback.");
                return true;
            }

            plugin.originalInitializeRequested = true;

            if (plugin.state == LoaderState.Ready || DIYLevelAssetBundleManager.IsInitialized)
            {
                plugin.state = LoaderState.Ready;
                return false;
            }

            if (plugin.state == LoaderState.Failed)
            {
                plugin.ScheduleSynchronousFallback();
                return false;
            }

            plugin.BeginAsyncInitialization("OC2DIYLevel Initialize() request");
            return false;
        }

        private static void RefreshDlcButtonsPostfix(FrontendDLCMenu __instance)
        {
            AsyncLevelLoaderPlugin plugin = pluginInstance;
            if (plugin != null && plugin.interceptEnabled)
            {
                plugin.lastDlcMenu = __instance;
            }
        }

        private static bool CustomArcadeAddUiPrefix()
        {
            AsyncLevelLoaderPlugin plugin = pluginInstance;
            if (plugin == null || !plugin.interceptEnabled)
            {
                return true;
            }

            return plugin.state == LoaderState.Ready || DIYLevelAssetBundleManager.IsInitialized;
        }

        private void BeginAsyncInitialization(string reason)
        {
            if (!interceptEnabled || state != LoaderState.Idle)
            {
                return;
            }

            state = LoaderState.Loading;
            currentStatus = "Preparing custom level bundles...";
            Logger.LogInfo("Starting asynchronous OC2DIYLevel initialization: " + reason + ".");
            activeInitializationCoroutine = StartCoroutine(InitializeAsync());
        }

        private IEnumerator InitializeAsync()
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            List<AssetBundle> loadedBundles = new List<AssetBundle>();
            activeLoadedBundles = loadedBundles;
            List<KeyValuePair<string, LevelSetInfoSO>> levelSetInfos = new List<KeyValuePair<string, LevelSetInfoSO>>();
            List<FileInfo> commonFiles;
            List<LevelBundleCandidate> levelCandidates;
            string rootPath;

            loadedLevelSets = 0;
            skippedDuplicateBundles = 0;
            missingInfoDirectories = 0;
            failedLevelBundles = 0;
            completedItems = 0;
            totalItems = 0;
            lastError = string.Empty;

            try
            {
                rootPath = Path.GetDirectoryName(typeof(DIYLevelPlugin).Assembly.Location);
                commonFiles = DiscoverAdditionalCommonBundles(rootPath);
                levelCandidates = DiscoverLevelBundles(Path.Combine(rootPath, "levels"));
                totalItems = 1 + commonFiles.Count + levelCandidates.Count;
            }
            catch (Exception exception)
            {
                AbortInitialization("Failed to enumerate OC2DIYLevel files: " + exception.Message, loadedBundles);
                yield break;
            }

            string commonPath = Path.Combine(rootPath, "common");
            if (!File.Exists(commonPath))
            {
                AbortInitialization("Missing required bundle: " + commonPath, loadedBundles);
                yield break;
            }

            currentStatus = "Loading common bundle";
            AssetBundleCreateRequest commonRequest = TryStartBundleRequest(commonPath);
            if (commonRequest == null)
            {
                AbortInitialization("Could not start loading the common bundle.", loadedBundles);
                yield break;
            }

            TrackOperation(commonRequest, 0f, 0.55f);
            yield return commonRequest;
            AssetBundle commonBundle = TryGetBundle(commonRequest, commonPath);
            if (commonBundle == null)
            {
                AbortInitialization("Failed to load required bundle: " + commonPath, loadedBundles);
                yield break;
            }
            loadedBundles.Add(commonBundle);

            currentStatus = "Loading custom level cover";
            AssetBundleRequest coverRequest = TryStartAssetRequest(commonBundle, "diylevelcover", typeof(Sprite));
            if (coverRequest == null)
            {
                AbortInitialization("Could not start loading diylevelcover.", loadedBundles);
                yield break;
            }
            TrackOperation(coverRequest, 0.55f, 0.15f);
            yield return coverRequest;
            Sprite cover = TryGetAsset(coverRequest, "diylevelcover") as Sprite;
            if (cover == null)
            {
                AbortInitialization("Missing required asset: diylevelcover.", loadedBundles);
                yield break;
            }

            currentStatus = "Loading DIY level game session";
            AssetBundleRequest sessionRequest = TryStartAssetRequest(commonBundle, "DIYLevelGameSession", typeof(GameObject));
            if (sessionRequest == null)
            {
                AbortInitialization("Could not start loading DIYLevelGameSession.", loadedBundles);
                yield break;
            }
            TrackOperation(sessionRequest, 0.70f, 0.15f);
            yield return sessionRequest;
            GameObject gameSessionPrefab = TryGetAsset(sessionRequest, "DIYLevelGameSession") as GameObject;
            if (gameSessionPrefab == null)
            {
                AbortInitialization("Missing required asset: DIYLevelGameSession.", loadedBundles);
                yield break;
            }

            currentStatus = "Loading level configuration template";
            AssetBundleRequest templateRequest = TryStartAssetRequest(commonBundle, "LevelConfigTemplateSO", typeof(PseudoPrefabSO));
            if (templateRequest == null)
            {
                AbortInitialization("Could not start loading LevelConfigTemplateSO.", loadedBundles);
                yield break;
            }
            TrackOperation(templateRequest, 0.85f, 0.15f);
            yield return templateRequest;
            PseudoPrefabSO configTemplate = TryGetAsset(templateRequest, "LevelConfigTemplateSO") as PseudoPrefabSO;
            if (configTemplate == null)
            {
                AbortInitialization("Missing required asset: LevelConfigTemplateSO.", loadedBundles);
                yield break;
            }

            CompleteCurrentItem();

            for (int index = 0; index < commonFiles.Count; index++)
            {
                FileInfo commonFile = commonFiles[index];
                currentStatus = string.Format("Loading shared bundle {0}/{1}: {2}", index + 1, commonFiles.Count, commonFile.Name);
                AssetBundleCreateRequest request = TryStartBundleRequest(commonFile.FullName);
                if (request == null)
                {
                    Logger.LogWarning("Could not start shared bundle request: " + commonFile.FullName);
                    CompleteCurrentItem();
                    continue;
                }

                TrackOperation(request, 0f, 1f);
                yield return request;
                AssetBundle bundle = TryGetBundle(request, commonFile.FullName);
                if (bundle != null)
                {
                    loadedBundles.Add(bundle);
                }
                else
                {
                    Logger.LogWarning("Shared bundle failed to load: " + commonFile.FullName);
                }
                CompleteCurrentItem();
                yield return null;
            }

            HashSet<string> successfullyLoadedInfoNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < levelCandidates.Count; index++)
            {
                LevelBundleCandidate candidate = levelCandidates[index];
                if (skipDuplicateInfoNames.Value && successfullyLoadedInfoNames.Contains(candidate.InfoFile.Name))
                {
                    skippedDuplicateBundles++;
                    currentStatus = string.Format(
                        "Skipping same-name conflict {0}/{1}: {2}",
                        index + 1,
                        levelCandidates.Count,
                        candidate.Directory.Name);
                    Logger.LogWarning(currentStatus + " [" + candidate.InfoFile.Name + "]");
                    CompleteCurrentItem();
                    yield return null;
                    continue;
                }

                currentStatus = string.Format("Loading level set {0}/{1}: {2}", index + 1, levelCandidates.Count, candidate.Directory.Name);
                Logger.LogInfo(currentStatus + " [" + candidate.InfoFile.Name + "]");

                AssetBundleCreateRequest request = TryStartBundleRequest(candidate.InfoFile.FullName);
                if (request == null)
                {
                    failedLevelBundles++;
                    CompleteCurrentItem();
                    continue;
                }

                TrackOperation(request, 0f, 0.85f);
                yield return request;
                AssetBundle bundle = TryGetBundle(request, candidate.InfoFile.FullName);
                if (bundle == null)
                {
                    failedLevelBundles++;
                    CompleteCurrentItem();
                    yield return null;
                    continue;
                }
                loadedBundles.Add(bundle);

                AssetBundleRequest infoRequest = TryStartAssetRequest(bundle, "LevelSetInfo", typeof(LevelSetInfoSO));
                if (infoRequest == null)
                {
                    failedLevelBundles++;
                    SafeUnloadBundle(bundle, true);
                    loadedBundles.Remove(bundle);
                    CompleteCurrentItem();
                    continue;
                }

                TrackOperation(infoRequest, 0.85f, 0.15f);
                yield return infoRequest;
                LevelSetInfoSO levelSetInfo = TryGetAsset(infoRequest, "LevelSetInfo") as LevelSetInfoSO;
                if (levelSetInfo == null)
                {
                    Logger.LogWarning("Missing LevelSetInfo asset in: " + candidate.InfoFile.FullName);
                    failedLevelBundles++;
                    SafeUnloadBundle(bundle, true);
                    loadedBundles.Remove(bundle);
                    CompleteCurrentItem();
                    yield return null;
                    continue;
                }

                levelSetInfos.Add(new KeyValuePair<string, LevelSetInfoSO>(candidate.Directory.FullName, levelSetInfo));
                successfullyLoadedInfoNames.Add(candidate.InfoFile.Name);
                loadedLevelSets++;
                CompleteCurrentItem();
                yield return null;
            }

            DLCFrontendData dlcFrontendData;
            try
            {
                dlcFrontendData = BuildDlcFrontendData(cover);
                CommitInitialization(commonBundle, cover, gameSessionPrefab, configTemplate, levelSetInfos, dlcFrontendData);
            }
            catch (Exception exception)
            {
                AbortInitialization("Failed to commit asynchronous initialization: " + exception.Message, loadedBundles);
                yield break;
            }

            retainedBundles.AddRange(loadedBundles);
            loadedBundles.Clear();
            activeLoadedBundles = null;
            activeInitializationCoroutine = null;
            currentOperation = null;
            operationBase = 0f;
            operationWeight = 0f;
            currentStatus = string.Format(
                "Ready: {0} level sets; skipped {1} conflicts; {2} failed.",
                loadedLevelSets,
                skippedDuplicateBundles,
                failedLevelBundles);
            state = LoaderState.Ready;
            readyMessageUntil = Time.realtimeSinceStartup + 6f;
            stopwatch.Stop();

            Logger.LogInfo(string.Format(
                "Asynchronous OC2DIYLevel initialization completed in {0:F2}s. Loaded={1}, skipped duplicate names={2}, missing info={3}, failed={4}.",
                stopwatch.Elapsed.TotalSeconds,
                loadedLevelSets,
                skippedDuplicateBundles,
                missingInfoDirectories,
                failedLevelBundles));

            StartCoroutine(RefreshMenusWhenAvailable());
        }

        private List<FileInfo> DiscoverAdditionalCommonBundles(string rootPath)
        {
            FileInfo[] discovered = new DirectoryInfo(rootPath).GetFiles("common*");
            List<FileInfo> result = new List<FileInfo>();
            for (int index = 0; index < discovered.Length; index++)
            {
                if (!string.Equals(discovered[index].Name, "common", StringComparison.Ordinal))
                {
                    result.Add(discovered[index]);
                }
            }
            return result;
        }

        private List<LevelBundleCandidate> DiscoverLevelBundles(string levelsPath)
        {
            List<LevelBundleCandidate> result = new List<LevelBundleCandidate>();
            if (!Directory.Exists(levelsPath))
            {
                Logger.LogWarning("Levels directory does not exist: " + levelsPath);
                return result;
            }

            DirectoryInfo[] directories = new DirectoryInfo(levelsPath).GetDirectories();
            for (int index = 0; index < directories.Length; index++)
            {
                DirectoryInfo directory = directories[index];
                FileInfo[] infoFiles = directory.GetFiles("info*");
                if (infoFiles.Length == 0)
                {
                    missingInfoDirectories++;
                    Logger.LogWarning("Skipping directory without info bundle: " + directory.FullName);
                    continue;
                }

                result.Add(new LevelBundleCandidate { Directory = directory, InfoFile = infoFiles[0] });
            }

            return result;
        }

        private AssetBundleCreateRequest TryStartBundleRequest(string path)
        {
            try
            {
                return AssetBundle.LoadFromFileAsync(path);
            }
            catch (Exception exception)
            {
                Logger.LogError("AssetBundle.LoadFromFileAsync failed for " + path + ": " + exception);
                return null;
            }
        }

        private AssetBundle TryGetBundle(AssetBundleCreateRequest request, string path)
        {
            try
            {
                AssetBundle bundle = request.assetBundle;
                if (bundle == null)
                {
                    Logger.LogWarning("Asset bundle request returned null: " + path);
                }
                return bundle;
            }
            catch (Exception exception)
            {
                Logger.LogError("Reading asset bundle request failed for " + path + ": " + exception);
                return null;
            }
        }

        private AssetBundleRequest TryStartAssetRequest(AssetBundle bundle, string assetName, Type assetType)
        {
            try
            {
                return bundle.LoadAssetAsync(assetName, assetType);
            }
            catch (Exception exception)
            {
                Logger.LogError("AssetBundle.LoadAssetAsync failed for " + assetName + ": " + exception);
                return null;
            }
        }

        private UnityEngine.Object TryGetAsset(AssetBundleRequest request, string assetName)
        {
            try
            {
                UnityEngine.Object asset = request.asset;
                if (asset == null)
                {
                    Logger.LogWarning("Asset request returned null: " + assetName);
                }
                return asset;
            }
            catch (Exception exception)
            {
                Logger.LogError("Reading asset request failed for " + assetName + ": " + exception);
                return null;
            }
        }

        private void TrackOperation(AsyncOperation operation, float baseProgress, float weight)
        {
            currentOperation = operation;
            operationBase = baseProgress;
            operationWeight = weight;
        }

        private void CompleteCurrentItem()
        {
            completedItems++;
            currentOperation = null;
            operationBase = 0f;
            operationWeight = 0f;
        }

        private DLCFrontendData BuildDlcFrontendData(Sprite cover)
        {
            DLCFrontendData data = null;
            try
            {
                data = ScriptableObject.CreateInstance<DLCFrontendData>();
                data.name = "DLC_DIYLevel";
                data.m_NameLocalizationKey = "\"More Levels\"";
                data.m_DescriptionLocalizationKey = OC2DIYLevel.UIUtils.GetLocalizedText(
                    "\"Enjoy extra levels from the community!\"",
                    "\"游玩来自玩家社区的更多关卡！\"");
                data.m_DLCID = 15;
                data.m_type = (DLCType)0;
                data.m_IsFreeDLC = true;
                data.m_IsSeasonPassDLC = false;
                data.m_PreviewImage = cover;
                return data;
            }
            catch
            {
                if (data != null)
                {
                    UnityEngine.Object.Destroy(data);
                }
                throw;
            }
        }

        private void CommitInitialization(
            AssetBundle commonBundle,
            Sprite cover,
            GameObject gameSessionPrefab,
            PseudoPrefabSO configTemplate,
            List<KeyValuePair<string, LevelSetInfoSO>> levelSetInfos,
            DLCFrontendData dlcFrontendData)
        {
            DIYLevelAssetBundleManager oldManager = managerInstanceField.GetValue(null) as DIYLevelAssetBundleManager;
            AssetBundle oldCommonBundle = commonBundleField.GetValue(null) as AssetBundle;
            Sprite oldCover = diyLevelCoverField.GetValue(null) as Sprite;
            GameObject oldGameSessionPrefab = diyLevelGameSessionPrefabField.GetValue(null) as GameObject;
            PseudoPrefabSO oldConfigTemplate = configTemplateSoField.GetValue(null) as PseudoPrefabSO;
            List<KeyValuePair<string, LevelSetInfoSO>> oldLevelSetInfos = DIYLevelAssetBundleManager.levelSetInfos;
            DLCFrontendData oldDlcFrontendData = DIYLevelAssetBundleManager.diyDLCFrontendData;
            GameObject managerObject = null;

            try
            {
                managerObject = new GameObject("DIYLevelAssetBundleManager");
                UnityEngine.Object.DontDestroyOnLoad(managerObject);
                DIYLevelAssetBundleManager manager = managerObject.AddComponent<DIYLevelAssetBundleManager>();

                managerInstanceField.SetValue(null, manager);
                diyLevelCoverField.SetValue(null, cover);
                diyLevelGameSessionPrefabField.SetValue(null, gameSessionPrefab);
                configTemplateSoField.SetValue(null, configTemplate);
                DIYLevelAssetBundleManager.levelSetInfos = levelSetInfos;
                DIYLevelAssetBundleManager.diyDLCFrontendData = dlcFrontendData;

                // IsInitialized only checks commonBundle. Publish it last so readers never see a partial list.
                commonBundleField.SetValue(null, commonBundle);
            }
            catch
            {
                commonBundleField.SetValue(null, oldCommonBundle);
                diyLevelCoverField.SetValue(null, oldCover);
                diyLevelGameSessionPrefabField.SetValue(null, oldGameSessionPrefab);
                configTemplateSoField.SetValue(null, oldConfigTemplate);
                managerInstanceField.SetValue(null, oldManager);
                DIYLevelAssetBundleManager.levelSetInfos = oldLevelSetInfos;
                DIYLevelAssetBundleManager.diyDLCFrontendData = oldDlcFrontendData;
                if (managerObject != null)
                {
                    UnityEngine.Object.Destroy(managerObject);
                }
                if (dlcFrontendData != null && dlcFrontendData != oldDlcFrontendData)
                {
                    UnityEngine.Object.Destroy(dlcFrontendData);
                }
                throw;
            }

            if (oldManager != null && oldManager.gameObject != managerObject)
            {
                UnityEngine.Object.Destroy(oldManager.gameObject);
            }
        }

        private void AbortInitialization(string message, List<AssetBundle> loadedBundles)
        {
            lastError = message;
            currentStatus = message;
            currentOperation = null;
            state = LoaderState.Failed;
            Logger.LogError(message);

            for (int index = loadedBundles.Count - 1; index >= 0; index--)
            {
                SafeUnloadBundle(loadedBundles[index], true);
            }
            loadedBundles.Clear();
            activeLoadedBundles = null;
            activeInitializationCoroutine = null;

            try
            {
                commonBundleField.SetValue(null, null);
                diyLevelCoverField.SetValue(null, null);
                diyLevelGameSessionPrefabField.SetValue(null, null);
                configTemplateSoField.SetValue(null, null);
                DIYLevelAssetBundleManager.levelSetInfos = new List<KeyValuePair<string, LevelSetInfoSO>>();
                DIYLevelAssetBundleManager.diyDLCFrontendData = null;
            }
            catch (Exception exception)
            {
                Logger.LogError("Failed to reset OC2DIYLevel fields after async failure: " + exception);
            }

            if (originalInitializeRequested)
            {
                ScheduleSynchronousFallback();
            }
        }

        private void ScheduleSynchronousFallback()
        {
            if (!fallbackToSynchronous.Value || fallbackScheduled || DIYLevelAssetBundleManager.IsInitialized)
            {
                return;
            }

            fallbackScheduled = true;
            fallbackCoroutine = StartCoroutine(RunSynchronousFallbackNextFrame());
        }

        private IEnumerator RunSynchronousFallbackNextFrame()
        {
            yield return null;
            fallbackScheduled = false;
            fallbackCoroutine = null;
            if (DIYLevelAssetBundleManager.IsInitialized)
            {
                state = LoaderState.Ready;
                yield break;
            }

            allowOriginalInitializeOnce = true;
            try
            {
                DIYLevelAssetBundleManager.Initialize();
                if (DIYLevelAssetBundleManager.IsInitialized)
                {
                    state = LoaderState.Ready;
                    currentStatus = "OC2DIYLevel original synchronous fallback completed.";
                    readyMessageUntil = Time.realtimeSinceStartup + 5f;
                    StartCoroutine(RefreshMenusWhenAvailable());
                }
            }
            catch (Exception exception)
            {
                Logger.LogError("OC2DIYLevel synchronous fallback failed: " + exception);
            }
            finally
            {
                allowOriginalInitializeOnce = false;
            }
        }

        private static void SafeUnloadBundle(AssetBundle bundle, bool unloadLoadedObjects)
        {
            if (bundle == null)
            {
                return;
            }

            try
            {
                bundle.Unload(unloadLoadedObjects);
            }
            catch
            {
                // Best-effort cleanup only. The original initializer remains available as a fallback.
            }
        }

        private IEnumerator RefreshMenusWhenAvailable()
        {
            for (int attempt = 0; attempt < 300; attempt++)
            {
                yield return null;
                if (state != LoaderState.Ready)
                {
                    yield break;
                }

                FrontendDLCMenu menu = lastDlcMenu;
                if (menu == null)
                {
                    menu = UnityEngine.Object.FindObjectOfType<FrontendDLCMenu>();
                }

                if (menu != null)
                {
                    try
                    {
                        refreshDlcButtonsMethod.Invoke(menu, null);
                        CustomArcadeEntryUI.AddUI();
                        Logger.LogInfo("Refreshed More Levels and Custom Arcade UI after asynchronous initialization.");
                    }
                    catch (Exception exception)
                    {
                        Logger.LogWarning("Refreshing frontend menus failed; the next normal menu refresh will retry: " + exception.Message);
                    }
                    yield break;
                }
            }
        }

        private bool ValidateSupportedInstallation()
        {
            try
            {
                Assembly diyLevelAssembly = typeof(DIYLevelPlugin).Assembly;
                if (diyLevelAssembly.ManifestModule.ModuleVersionId != SupportedDiyLevelMvid)
                {
                    Logger.LogError("Unsupported OC2DIYLevel MVID: " + diyLevelAssembly.ManifestModule.ModuleVersionId);
                    return false;
                }

                string actualHash = ComputeSha256(diyLevelAssembly.Location);
                if (!string.Equals(actualHash, SupportedDiyLevelSha256, StringComparison.OrdinalIgnoreCase))
                {
                    Logger.LogError("Unsupported OC2DIYLevel SHA-256: " + actualHash);
                    return false;
                }

                Type managerType = typeof(DIYLevelAssetBundleManager);
                BindingFlags staticFlags = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
                initializeMethod = managerType.GetMethod("Initialize", staticFlags, null, Type.EmptyTypes, null);
                managerInstanceField = managerType.GetField("Instance", staticFlags);
                commonBundleField = managerType.GetField("commonBundle", staticFlags);
                diyLevelCoverField = managerType.GetField("diyLevelCover", staticFlags);
                diyLevelGameSessionPrefabField = managerType.GetField("diyLevelGameSessionPrefab", staticFlags);
                configTemplateSoField = managerType.GetField("configTemplateSO", staticFlags);
                refreshDlcButtonsMethod = AccessTools.Method(typeof(FrontendDLCMenu), "RefreshDLCButtons", Type.EmptyTypes);
                customArcadeAddUiMethod = AccessTools.Method(typeof(CustomArcadeEntryUI), "AddUI", Type.EmptyTypes);

                if (initializeMethod == null ||
                    managerInstanceField == null ||
                    commonBundleField == null ||
                    diyLevelCoverField == null ||
                    diyLevelGameSessionPrefabField == null ||
                    configTemplateSoField == null ||
                    refreshDlcButtonsMethod == null ||
                    customArcadeAddUiMethod == null)
                {
                    Logger.LogError("OC2DIYLevel 0.9.0 compatibility members are missing.");
                    return false;
                }

                if (commonBundleField.FieldType != typeof(AssetBundle) ||
                    diyLevelCoverField.FieldType != typeof(Sprite) ||
                    diyLevelGameSessionPrefabField.FieldType != typeof(GameObject) ||
                    configTemplateSoField.FieldType != typeof(PseudoPrefabSO))
                {
                    Logger.LogError("OC2DIYLevel 0.9.0 compatibility field types do not match.");
                    return false;
                }

                return true;
            }
            catch (Exception exception)
            {
                Logger.LogError("OC2DIYLevel compatibility validation failed: " + exception);
                return false;
            }
        }

        private static string ComputeSha256(string path)
        {
            using (FileStream stream = File.OpenRead(path))
            using (SHA256 sha256 = SHA256.Create())
            {
                byte[] hash = sha256.ComputeHash(stream);
                StringBuilder builder = new StringBuilder(hash.Length * 2);
                for (int index = 0; index < hash.Length; index++)
                {
                    builder.Append(hash[index].ToString("X2"));
                }
                return builder.ToString();
            }
        }

        private float GetDisplayedProgress()
        {
            if (state == LoaderState.Ready)
            {
                return 1f;
            }
            if (totalItems <= 0)
            {
                return 0f;
            }

            float currentItemProgress = operationBase;
            if (currentOperation != null)
            {
                currentItemProgress += operationWeight * currentOperation.progress;
            }
            return Mathf.Clamp01((completedItems + currentItemProgress) / totalItems);
        }

        private void OnGUI()
        {
            if (showProgress == null || !showProgress.Value)
            {
                return;
            }

            bool showLoading = state == LoaderState.Loading;
            bool showReady = state == LoaderState.Ready && Time.realtimeSinceStartup < readyMessageUntil;
            bool showFailure = state == LoaderState.Failed && !fallbackToSynchronous.Value;
            if (!showLoading && !showReady && !showFailure)
            {
                return;
            }

            EnsureGuiStyles();

            float width = Mathf.Min(520f, Screen.width - 40f);
            float height = 96f;
            Rect panel = new Rect((Screen.width - width) * 0.5f, 24f, width, height);
            GUI.Box(panel, GUIContent.none);

            string title;
            string detail;
            float progress;
            if (showLoading)
            {
                progress = GetDisplayedProgress();
                title = string.Format("自定义关卡异步加载  {0:P0}", progress);
                detail = currentStatus;
            }
            else if (showReady)
            {
                progress = 1f;
                title = "自定义关卡已就绪";
                detail = currentStatus;
            }
            else
            {
                progress = 0f;
                title = "自定义关卡异步加载失败";
                detail = lastError;
            }

            GUI.Label(new Rect(panel.x + 14f, panel.y + 8f, panel.width - 28f, 24f), title, titleStyle);
            GUI.Label(new Rect(panel.x + 14f, panel.y + 34f, panel.width - 28f, 22f), detail, detailStyle);

            Rect bar = new Rect(panel.x + 14f, panel.y + 65f, panel.width - 28f, 16f);
            GUI.Box(bar, GUIContent.none);
            Color oldColor = GUI.color;
            GUI.color = showFailure ? new Color(0.85f, 0.25f, 0.25f, 1f) : new Color(0.35f, 0.85f, 0.95f, 1f);
            GUI.Box(new Rect(bar.x + 2f, bar.y + 2f, Mathf.Max(0f, (bar.width - 4f) * progress), bar.height - 4f), GUIContent.none);
            GUI.color = oldColor;
            GUI.Label(bar, string.Format("{0:P0}", progress), centerStyle);
        }

        private void EnsureGuiStyles()
        {
            if (titleStyle != null)
            {
                return;
            }

            titleStyle = new GUIStyle(GUI.skin.label);
            titleStyle.fontSize = 16;
            titleStyle.fontStyle = FontStyle.Bold;
            titleStyle.alignment = TextAnchor.MiddleLeft;

            detailStyle = new GUIStyle(GUI.skin.label);
            detailStyle.fontSize = 12;
            detailStyle.alignment = TextAnchor.MiddleLeft;
            detailStyle.clipping = TextClipping.Clip;

            centerStyle = new GUIStyle(GUI.skin.label);
            centerStyle.fontSize = 11;
            centerStyle.alignment = TextAnchor.MiddleCenter;
            centerStyle.normal.textColor = Color.white;
        }
    }
}
