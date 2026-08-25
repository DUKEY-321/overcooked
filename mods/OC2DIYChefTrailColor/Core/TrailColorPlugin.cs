using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using BepInEx;
using BepInEx.Configuration;
using HarmonyLib;
using OC2DIYChef;
using UnityEngine;

namespace OC2DIYChefTrailColor
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    [BepInDependency("com.ch3ngyz.plugin.HostUtilities", BepInDependency.DependencyFlags.HardDependency)]
    [BepInDependency("dev.gua.overcooked.diychef", BepInDependency.DependencyFlags.HardDependency)]
    [BepInProcess("Overcooked2.exe")]
    public sealed class TrailColorPlugin : BaseUnityPlugin
    {
        public const string PluginGuid = "local.oc2.diycheftrailcolor";
        public const string PluginName = "OC2 DIY Chef Trail Color by DUKEY";
        public const string PluginVersion = "0.2.2";

        private const string HostTypeName = "HostUtilities.GameplayDashSmokeColour";
        private const string SignHeadName = "Chef_Sign";
        private const string SignStableKey = "diy:174:Chef_Sign";
        private const string SignConfigSection = "Character.Sign";
        private const byte SignId = 174;
        private const float RefreshDelaySeconds = 0.05f;

        private static TrailColorPlugin instance;

        private readonly Dictionary<string, TrailColorProfile> profiles =
            new Dictionary<string, TrailColorProfile>(StringComparer.Ordinal);
        private readonly HashSet<string> loggedMatches =
            new HashSet<string>(StringComparer.Ordinal);
        private readonly HashSet<string> loggedIdentityWarnings =
            new HashSet<string>(StringComparer.Ordinal);

        private Harmony harmony;
        private MethodInfo resolveDashColourMethod;
        private MethodInfo applyParticleColorMethod;
        private bool refreshRequested;
        private bool refreshScheduled;
        private float refreshAt;
        private bool configurationSaveRequested;

        public static TrailColorPlugin Instance
        {
            get { return instance; }
        }

        public IList<TrailColorProfile> Profiles
        {
            get
            {
                List<TrailColorProfile> result =
                    new List<TrailColorProfile>(profiles.Values);
                result.Sort(CompareProfiles);
                return result.AsReadOnly();
            }
        }

        private void Awake()
        {
            instance = this;
            Config.SaveOnConfigSet = false;

            RegisterProfile(
                SignStableKey,
                "Sign",
                "一二 / Sign",
                SignHeadName,
                true,
                SignId,
                SignConfigSection,
                true,
                new Color(1f, 176f / 255f, 208f / 255f, 1f),
                new Color(1f, 79f / 255f, 163f / 255f, 1f),
                false);

            ScanInstalledCharacters();
            Config.Save();

            if (!InstallPatch())
            {
                Logger.LogError(
                    "Character trail-colour patch is disabled; " +
                    "HostUtilities 1.8.0 API was not found.");
                return;
            }

            Logger.LogInfo(
                "Installed character trail-colour resolver for " +
                profiles.Count + " character profile(s).");
        }

        private void Update()
        {
            if (configurationSaveRequested)
            {
                configurationSaveRequested = false;
                Config.Save();
            }

            if (refreshRequested)
            {
                refreshRequested = false;
                refreshScheduled = true;
                refreshAt = Time.realtimeSinceStartup + RefreshDelaySeconds;
            }

            if (refreshScheduled && Time.realtimeSinceStartup >= refreshAt)
            {
                refreshScheduled = false;
                RefreshRunningSmoke();
            }
        }

        private void OnDestroy()
        {
            if (harmony != null)
            {
                harmony.UnpatchAll(PluginGuid);
                harmony = null;
            }

            if (ReferenceEquals(instance, this))
            {
                instance = null;
            }
        }

        private static int CompareProfiles(
            TrailColorProfile left,
            TrailColorProfile right)
        {
            int result = GetSortGroup(left).CompareTo(GetSortGroup(right));
            if (result != 0)
            {
                return result;
            }

            if (left.IsDiy && right.IsDiy)
            {
                result = left.DiyId.CompareTo(right.DiyId);
                if (result != 0)
                {
                    return result;
                }
            }

            result = string.Compare(
                left.DisplayName,
                right.DisplayName,
                StringComparison.OrdinalIgnoreCase);
            if (result != 0)
            {
                return result;
            }

            return string.Compare(
                left.StableKey,
                right.StableKey,
                StringComparison.Ordinal);
        }

        private static int GetSortGroup(TrailColorProfile profile)
        {
            if (profile.StableKey == SignStableKey)
            {
                return 0;
            }

            return profile.IsDiy ? 1 : 2;
        }

        private void ScanInstalledCharacters()
        {
            string diyChefDirectory;
            try
            {
                diyChefDirectory = Path.GetDirectoryName(
                    typeof(DIYChefAvatarData).Assembly.Location);
            }
            catch (Exception exception)
            {
                Logger.LogWarning(
                    "Could not locate OC2DIYChef installation: " +
                    exception.Message);
                return;
            }

            if (string.IsNullOrEmpty(diyChefDirectory))
            {
                Logger.LogWarning("OC2DIYChef installation directory is empty.");
                return;
            }

            ScanDiyCharacterResources(
                Path.Combine(diyChefDirectory, "Resources"));
            ScanOfficialCharacterList(
                Path.Combine(diyChefDirectory, "official-all.txt"));
        }

        private void ScanOfficialCharacterList(string path)
        {
            if (!File.Exists(path))
            {
                Logger.LogWarning(
                    "Official character list was not found: " + path);
                return;
            }

            try
            {
                string[] lines = File.ReadAllLines(path);
                for (int index = 0; index < lines.Length; index++)
                {
                    string headName = lines[index].Trim();
                    if (headName.Length == 0 ||
                        headName.StartsWith("#", StringComparison.Ordinal) ||
                        headName.StartsWith(";", StringComparison.Ordinal))
                    {
                        continue;
                    }

                    RegisterOfficialProfile(headName, false);
                }
            }
            catch (Exception exception)
            {
                Logger.LogWarning(
                    "Could not scan official character list: " +
                    exception.Message);
            }
        }

        private void ScanDiyCharacterResources(string resourcesDirectory)
        {
            if (!Directory.Exists(resourcesDirectory))
            {
                Logger.LogWarning(
                    "DIY character resources directory was not found: " +
                    resourcesDirectory);
                return;
            }

            string[] directories;
            try
            {
                directories = Directory.GetDirectories(resourcesDirectory);
            }
            catch (Exception exception)
            {
                Logger.LogWarning(
                    "Could not enumerate DIY character resources: " +
                    exception.Message);
                return;
            }

            for (int index = 0; index < directories.Length; index++)
            {
                string directory = directories[index];
                string infoPath = Path.Combine(directory, "INFO");
                if (!File.Exists(infoPath))
                {
                    continue;
                }

                byte id;
                if (!TryReadDiyId(infoPath, out id) || id == byte.MaxValue)
                {
                    Logger.LogWarning(
                        "Skipped DIY character with invalid ID: " + directory);
                    continue;
                }

                string resourceName = new DirectoryInfo(directory).Name;
                string headName = resourceName.StartsWith(
                    "Chef_",
                    StringComparison.Ordinal)
                    ? resourceName
                    : "Chef_" + resourceName;

                if (id == SignId && headName == SignHeadName)
                {
                    continue;
                }

                RegisterDiyProfile(
                    id,
                    headName,
                    resourceName,
                    false);
            }
        }

        private static bool TryReadDiyId(string infoPath, out byte id)
        {
            id = byte.MaxValue;
            try
            {
                string[] lines = File.ReadAllLines(infoPath);
                for (int index = 0; index < lines.Length; index++)
                {
                    string line = lines[index].Trim();
                    if (!line.StartsWith("ID=", StringComparison.Ordinal))
                    {
                        continue;
                    }

                    byte parsedId;
                    if (byte.TryParse(line.Substring(3).Trim(), out parsedId))
                    {
                        id = parsedId;
                        return true;
                    }
                }
            }
            catch
            {
                return false;
            }

            return false;
        }

        private TrailColorProfile RegisterOfficialProfile(
            string headName,
            bool requestConfigurationSave)
        {
            if (string.IsNullOrEmpty(headName))
            {
                return null;
            }

            string stableKey = "official:" + headName;
            return RegisterProfile(
                stableKey,
                headName,
                MakeDisplayName(headName),
                headName,
                false,
                byte.MaxValue,
                "Character.official." + MakeConfigToken(headName),
                false,
                Color.white,
                Color.white,
                requestConfigurationSave);
        }

        private TrailColorProfile RegisterDiyProfile(
            byte id,
            string headName,
            string displayName,
            bool requestConfigurationSave)
        {
            if (id == byte.MaxValue || string.IsNullOrEmpty(headName))
            {
                return null;
            }

            string resourceKey = headName.StartsWith(
                "Chef_",
                StringComparison.Ordinal)
                ? headName.Substring(5)
                : headName;
            string stableKey =
                "diy:" + id.ToString() + ":" + headName;
            string section =
                "Character.diy." + id.ToString() + "." +
                MakeConfigToken(resourceKey);
            return RegisterProfile(
                stableKey,
                resourceKey,
                string.IsNullOrEmpty(displayName) ? resourceKey : displayName,
                headName,
                true,
                id,
                section,
                false,
                Color.white,
                Color.white,
                requestConfigurationSave);
        }

        private TrailColorProfile RegisterProfile(
            string stableKey,
            string key,
            string displayName,
            string headName,
            bool isDiy,
            byte diyId,
            string section,
            bool defaultEnabled,
            Color defaultWalkColor,
            Color defaultDashColor,
            bool requestConfigurationSave)
        {
            TrailColorProfile existing;
            if (profiles.TryGetValue(stableKey, out existing))
            {
                return existing;
            }

            ConfigEntry<bool> enabled = Config.Bind(
                section,
                "Enabled",
                defaultEnabled,
                "Use character-specific trail colours for " +
                displayName + " (" + stableKey + ").");
            ConfigEntry<Color> walkColor = Config.Bind(
                section,
                "WalkColor",
                ForceOpaque(defaultWalkColor),
                "Running smoke colour. Alpha is fixed to 1 by HostUtilities.");
            ConfigEntry<Color> dashColor = Config.Bind(
                section,
                "DashColor",
                ForceOpaque(defaultDashColor),
                "Dash trail colour. Alpha is fixed to 1 by HostUtilities.");

            TrailColorProfile profile = new TrailColorProfile(
                stableKey,
                key,
                displayName,
                headName,
                isDiy,
                diyId,
                enabled,
                walkColor,
                dashColor,
                ForceOpaque(defaultWalkColor),
                ForceOpaque(defaultDashColor));

            enabled.SettingChanged += OnProfileSettingChanged;
            walkColor.SettingChanged += OnProfileSettingChanged;
            dashColor.SettingChanged += OnProfileSettingChanged;
            profiles.Add(stableKey, profile);

            if (requestConfigurationSave)
            {
                configurationSaveRequested = true;
            }

            return profile;
        }

        private void OnProfileSettingChanged(object sender, EventArgs eventArgs)
        {
            refreshRequested = true;
        }

        private bool InstallPatch()
        {
            Type hostType = AccessTools.TypeByName(HostTypeName);
            if (hostType == null)
            {
                Logger.LogError("Could not resolve " + HostTypeName + ".");
                return false;
            }

            Type[] resolveParameters =
            {
                typeof(GameObject),
                typeof(PlayerControls),
                typeof(bool)
            };
            resolveDashColourMethod = AccessTools.Method(
                hostType,
                "ResolveDashColour",
                resolveParameters);
            applyParticleColorMethod = AccessTools.Method(
                hostType,
                "ApplyParticleColor",
                new[] { typeof(GameObject), typeof(Color) });
            MethodInfo postfixMethod = AccessTools.Method(
                typeof(ResolveDashColourPatch),
                "Postfix");

            if (resolveDashColourMethod == null ||
                applyParticleColorMethod == null ||
                postfixMethod == null)
            {
                Logger.LogError(
                    "HostUtilities trail-colour signatures differ from " +
                    "1.8.0; refusing an unsafe patch.");
                return false;
            }

            HarmonyMethod postfix = new HarmonyMethod(postfixMethod);
            postfix.priority = Priority.Last;
            harmony = new Harmony(PluginGuid);
            harmony.Patch(resolveDashColourMethod, null, postfix);
            return true;
        }

        internal static void ResolveColorPostfix(
            GameObject playerObject,
            PlayerControls controls,
            bool dash,
            ref Color result)
        {
            TrailColorPlugin plugin = instance;
            if (plugin == null || playerObject == null)
            {
                return;
            }

            ChefAvatarData avatar;
            if (!TryGetChefAvatar(playerObject, controls, out avatar))
            {
                return;
            }

            TrailColorProfile profile = plugin.GetOrRegisterProfile(avatar);
            if (profile == null || !profile.Enabled)
            {
                return;
            }

            Color characterColor = ForceOpaque(
                dash ? profile.DashColor : profile.WalkColor);
            result = characterColor;
            plugin.LogMatchOnce(profile, dash, characterColor);
        }

        private TrailColorProfile GetOrRegisterProfile(ChefAvatarData avatar)
        {
            if (avatar == null || string.IsNullOrEmpty(avatar.HeadName))
            {
                LogIdentityWarningOnce(
                    "missing-head-name",
                    "Could not register a character with an empty HeadName.");
                return null;
            }

            DIYChefAvatarData diyChef = avatar as DIYChefAvatarData;
            if (diyChef != null)
            {
                if (diyChef.id == byte.MaxValue)
                {
                    LogIdentityWarningOnce(
                        "invalid-diy:" + avatar.HeadName,
                        "Could not register DIY character with ID 255: " +
                        avatar.HeadName + ".");
                    return null;
                }

                string stableKey =
                    "diy:" + diyChef.id.ToString() + ":" + avatar.HeadName;
                TrailColorProfile diyProfile;
                if (profiles.TryGetValue(stableKey, out diyProfile))
                {
                    return diyProfile;
                }

                diyProfile = RegisterDiyProfile(
                    diyChef.id,
                    avatar.HeadName,
                    MakeDisplayName(avatar.HeadName),
                    true);
                if (diyProfile != null)
                {
                    Logger.LogInfo(
                        "Registered runtime DIY character profile: " +
                        diyProfile.StableKey + ".");
                }
                return diyProfile;
            }

            string officialStableKey = "official:" + avatar.HeadName;
            TrailColorProfile officialProfile;
            if (profiles.TryGetValue(officialStableKey, out officialProfile))
            {
                return officialProfile;
            }

            officialProfile = RegisterOfficialProfile(avatar.HeadName, true);
            if (officialProfile != null)
            {
                Logger.LogInfo(
                    "Registered runtime official character profile: " +
                    officialProfile.StableKey + ".");
            }
            return officialProfile;
        }

        private void LogIdentityWarningOnce(string key, string message)
        {
            if (loggedIdentityWarnings.Add(key))
            {
                Logger.LogWarning(message);
            }
        }

        private void LogMatchOnce(
            TrailColorProfile profile,
            bool dash,
            Color color)
        {
            string key = profile.StableKey + (dash ? "|dash" : "|walk");
            if (!loggedMatches.Add(key))
            {
                return;
            }

            Logger.LogInfo(
                "Applied character colour: key=" + profile.StableKey +
                ", effect=" + (dash ? "dash" : "walk") +
                ", rgba=" + ColorUtility.ToHtmlStringRGBA(color) + ".");
        }

        public bool TryGetProfile(
            string stableKey,
            out TrailColorProfile profile)
        {
            return profiles.TryGetValue(stableKey, out profile);
        }

        public bool TryGetProfile(byte id, out TrailColorProfile profile)
        {
            foreach (TrailColorProfile candidate in profiles.Values)
            {
                if (candidate.IsDiy && candidate.DiyId == id)
                {
                    profile = candidate;
                    return true;
                }
            }

            profile = null;
            return false;
        }

        public bool TryGetColor(
            string stableKey,
            bool dash,
            out Color color)
        {
            TrailColorProfile profile;
            if (!profiles.TryGetValue(stableKey, out profile) ||
                !profile.Enabled)
            {
                color = Color.white;
                return false;
            }

            color = ForceOpaque(dash ? profile.DashColor : profile.WalkColor);
            return true;
        }

        public bool TryGetColor(byte id, bool dash, out Color color)
        {
            TrailColorProfile profile;
            if (!TryGetProfile(id, out profile) || !profile.Enabled)
            {
                color = Color.white;
                return false;
            }

            color = ForceOpaque(dash ? profile.DashColor : profile.WalkColor);
            return true;
        }

        public void RequestRefresh()
        {
            refreshRequested = true;
        }

        public void SaveConfiguration()
        {
            Config.Save();
        }

        public void RefreshRunningSmoke()
        {
            if (resolveDashColourMethod == null ||
                applyParticleColorMethod == null)
            {
                return;
            }

            PlayerControls[] controlsList =
                UnityEngine.Object.FindObjectsOfType<PlayerControls>();
            int recolored = 0;
            for (int index = 0; index < controlsList.Length; index++)
            {
                PlayerControls controls = controlsList[index];
                if (controls == null)
                {
                    continue;
                }

                GameObject playerObject = controls.gameObject;
                Transform runningPuff = FindChildRecursive(
                    controls.transform,
                    "PFX_RunningPuff");
                if (runningPuff == null)
                {
                    continue;
                }

                try
                {
                    Color walkColor = (Color)resolveDashColourMethod.Invoke(
                        null,
                        new object[] { playerObject, controls, false });
                    applyParticleColorMethod.Invoke(
                        null,
                        new object[] { runningPuff.gameObject, walkColor });
                    recolored++;
                }
                catch (Exception exception)
                {
                    Logger.LogWarning(
                        "Could not refresh running smoke: " +
                        exception.Message);
                }
            }

            if (recolored > 0)
            {
                Logger.LogDebug(
                    "Refreshed running smoke for " + recolored +
                    " player(s).");
            }
        }

        private static bool TryGetChefAvatar(
            GameObject playerObject,
            PlayerControls controls,
            out ChefAvatarData avatar)
        {
            avatar = null;
            ChefMeshReplacer replacer =
                playerObject.GetComponent<ChefMeshReplacer>();
            if (replacer == null && controls != null)
            {
                replacer = controls.GetComponent<ChefMeshReplacer>();
            }
            if (replacer == null)
            {
                replacer =
                    playerObject.GetComponentInChildren<ChefMeshReplacer>();
            }
            if (replacer == null)
            {
                return false;
            }

            GameSession.SelectedChefData selectedChef =
                replacer.GetChefData();
            if (selectedChef == null || selectedChef.Character == null)
            {
                return false;
            }

            avatar = selectedChef.Character;
            return true;
        }

        private static string MakeDisplayName(string headName)
        {
            string displayName = headName;
            if (displayName.StartsWith("Chef_", StringComparison.Ordinal))
            {
                displayName = displayName.Substring(5);
            }

            return displayName.Replace('_', ' ');
        }

        private static string MakeConfigToken(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "unknown";
            }

            return value
                .Replace('\r', '_')
                .Replace('\n', '_')
                .Replace('\t', '_')
                .Replace('=', '_')
                .Replace('[', '_')
                .Replace(']', '_');
        }

        private static Transform FindChildRecursive(
            Transform parent,
            string childName)
        {
            if (parent == null)
            {
                return null;
            }

            for (int index = 0; index < parent.childCount; index++)
            {
                Transform child = parent.GetChild(index);
                if (child.name == childName)
                {
                    return child;
                }

                Transform nested = FindChildRecursive(child, childName);
                if (nested != null)
                {
                    return nested;
                }
            }

            return null;
        }

        internal static Color ForceOpaque(Color color)
        {
            color.a = 1f;
            return color;
        }
    }

    public sealed class TrailColorProfile
    {
        private readonly ConfigEntry<bool> enabled;
        private readonly ConfigEntry<Color> walkColor;
        private readonly ConfigEntry<Color> dashColor;

        internal TrailColorProfile(
            string stableKey,
            string key,
            string displayName,
            string headName,
            bool isDiy,
            byte diyId,
            ConfigEntry<bool> enabled,
            ConfigEntry<Color> walkColor,
            ConfigEntry<Color> dashColor,
            Color defaultWalkColor,
            Color defaultDashColor)
        {
            StableKey = stableKey;
            Key = key;
            DisplayName = displayName;
            HeadName = headName;
            IsDiy = isDiy;
            DiyId = diyId;
            this.enabled = enabled;
            this.walkColor = walkColor;
            this.dashColor = dashColor;
            DefaultWalkColor = defaultWalkColor;
            DefaultDashColor = defaultDashColor;
        }

        public string StableKey { get; private set; }

        public string Key { get; private set; }

        public string DisplayName { get; private set; }

        public string HeadName { get; private set; }

        public bool IsDiy { get; private set; }

        public byte DiyId { get; private set; }

        public byte Id
        {
            get { return DiyId; }
        }

        public Color DefaultWalkColor { get; private set; }

        public Color DefaultDashColor { get; private set; }

        public bool Enabled
        {
            get { return enabled.Value; }
            set { enabled.Value = value; }
        }

        public Color WalkColor
        {
            get { return TrailColorPlugin.ForceOpaque(walkColor.Value); }
            set
            {
                walkColor.Value = TrailColorPlugin.ForceOpaque(value);
            }
        }

        public Color DashColor
        {
            get { return TrailColorPlugin.ForceOpaque(dashColor.Value); }
            set
            {
                dashColor.Value = TrailColorPlugin.ForceOpaque(value);
            }
        }

        public void ResetColors()
        {
            WalkColor = DefaultWalkColor;
            DashColor = DefaultDashColor;
        }
    }

    internal static class ResolveDashColourPatch
    {
        internal static void Postfix(
            GameObject playerObject,
            PlayerControls controls,
            bool dash,
            ref Color __result)
        {
            TrailColorPlugin.ResolveColorPostfix(
                playerObject,
                controls,
                dash,
                ref __result);
        }
    }
}
