import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { useApi } from "@/lib/utils";
import {
    Key,
    Plus,
    Trash2,
    Eye,
    EyeOff,
    Check,
    X,
    RefreshCw,
} from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

interface APIKey {
    id: string;
    provider: string;
    provider_name: string;
    label: string | null;
    display_suffix: string;
    is_active: boolean;
    created_at: string;
    last_used_at: string | null;
}

interface Provider {
    id: string;
    name: string;
    description: string;
    has_user_key: boolean;
    has_system_key: boolean;
}

interface APIKeysSettingsProps {
    userId: string;
}

export function APIKeysSettings({ userId }: APIKeysSettingsProps) {
    const { toast } = useToast();
    const { apiGet, apiPost, apiPatch, apiDelete } = useApi();

    const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
    const [providers, setProviders] = useState<Provider[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

    // Add key form state
    const [selectedProvider, setSelectedProvider] = useState("");
    const [apiKeyValue, setApiKeyValue] = useState("");
    const [keyLabel, setKeyLabel] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [showKeyInput, setShowKeyInput] = useState(false);

    useEffect(() => {
        loadData();
    }, [userId]);

    const loadData = async () => {
        setIsLoading(true);
        try {
            const [keysData, providersData] = await Promise.all([
                apiGet<APIKey[]>("/api-keys"),
                apiGet<{ providers: Provider[] }>("/api-keys/providers"),
            ]);
            setApiKeys(keysData || []);
            setProviders(providersData?.providers || []);
        } catch (error) {
            console.error("Failed to load API keys:", error);
            toast({
                title: "Error",
                description: "Failed to load API keys.",
                variant: "destructive",
            });
        } finally {
            setIsLoading(false);
        }
    };

    const handleAddKey = async () => {
        if (!selectedProvider || !apiKeyValue.trim()) {
            toast({
                title: "Missing fields",
                description: "Please select a provider and enter your API key.",
                variant: "destructive",
            });
            return;
        }

        setIsSubmitting(true);
        try {
            await apiPost("/api-keys", {
                provider: selectedProvider,
                api_key: apiKeyValue.trim(),
                label: keyLabel.trim() || null,
            });

            toast({
                title: "API Key Added",
                description: "Your API key has been securely stored.",
            });

            // Reset form
            setSelectedProvider("");
            setApiKeyValue("");
            setKeyLabel("");
            setIsAddDialogOpen(false);
            setShowKeyInput(false);

            // Reload data
            loadData();
        } catch (error: any) {
            toast({
                title: "Failed to add key",
                description: error?.message || "An error occurred.",
                variant: "destructive",
            });
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleToggleActive = async (key: APIKey) => {
        try {
            await apiPatch(`/api-keys/${key.id}`, { is_active: !key.is_active });
            setApiKeys((prev) =>
                prev.map((k) =>
                    k.id === key.id ? { ...k, is_active: !k.is_active } : k
                )
            );
            toast({
                title: key.is_active ? "Key Deactivated" : "Key Activated",
                description: `${key.provider_name} key is now ${key.is_active ? "inactive" : "active"}.`,
            });
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to update key status.",
                variant: "destructive",
            });
        }
    };

    const handleDeleteKey = async (key: APIKey) => {
        try {
            await apiDelete(`/api-keys/${key.id}`);
            setApiKeys((prev) => prev.filter((k) => k.id !== key.id));
            toast({
                title: "Key Deleted",
                description: `${key.provider_name} key has been removed.`,
            });
            loadData(); // Refresh providers status
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to delete key.",
                variant: "destructive",
            });
        }
    };

    const getProviderBadgeColor = (provider: Provider) => {
        if (provider.has_user_key) return "bg-green-500/20 text-green-400 border-green-500/30";
        return "bg-gray-500/20 text-gray-400 border-gray-500/30";
    };

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return "Never";
        return new Date(dateStr).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    };

    // Get providers that don't have a user key yet
    const availableProviders = providers.filter((p) => !p.has_user_key);

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Key className="w-5 h-5 text-primary" />
                        <CardTitle>API Keys</CardTitle>
                    </div>
                    <div className="flex gap-2">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={loadData}
                            disabled={isLoading}
                        >
                            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                        </Button>
                        <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
                            <DialogTrigger asChild>
                                <Button size="sm">
                                    <Plus className="w-4 h-4 mr-1" />
                                    Add Key
                                </Button>
                            </DialogTrigger>
                            <DialogContent>
                                <DialogHeader>
                                    <DialogTitle>Add API Key</DialogTitle>
                                    <DialogDescription>
                                        Add your own API key for an LLM provider. Keys are encrypted
                                        and stored securely.
                                    </DialogDescription>
                                </DialogHeader>

                                <div className="space-y-4 py-4">
                                    <div className="space-y-2">
                                        <Label>Provider</Label>
                                        <Select
                                            value={selectedProvider}
                                            onValueChange={setSelectedProvider}
                                        >
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select a provider" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {availableProviders.length === 0 ? (
                                                    <div className="py-2 px-3 text-sm text-muted-foreground">
                                                        All providers configured
                                                    </div>
                                                ) : (
                                                    availableProviders.map((provider) => (
                                                        <SelectItem key={provider.id} value={provider.id}>
                                                            <span>{provider.name}</span>
                                                        </SelectItem>
                                                    ))
                                                )}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div className="space-y-2">
                                        <Label>API Key</Label>
                                        <div className="relative">
                                            <Input
                                                type={showKeyInput ? "text" : "password"}
                                                placeholder="sk-..."
                                                value={apiKeyValue}
                                                onChange={(e) => setApiKeyValue(e.target.value)}
                                                className="pr-10"
                                            />
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                className="absolute right-0 top-0 h-full"
                                                onClick={() => setShowKeyInput(!showKeyInput)}
                                            >
                                                {showKeyInput ? (
                                                    <EyeOff className="w-4 h-4" />
                                                ) : (
                                                    <Eye className="w-4 h-4" />
                                                )}
                                            </Button>
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <Label>Label (Optional)</Label>
                                        <Input
                                            placeholder="e.g., Personal, Work, Project X"
                                            value={keyLabel}
                                            onChange={(e) => setKeyLabel(e.target.value)}
                                        />
                                    </div>
                                </div>

                                <DialogFooter>
                                    <Button
                                        variant="outline"
                                        onClick={() => setIsAddDialogOpen(false)}
                                    >
                                        Cancel
                                    </Button>
                                    <Button onClick={handleAddKey} disabled={isSubmitting}>
                                        {isSubmitting ? "Adding..." : "Add Key"}
                                    </Button>
                                </DialogFooter>
                            </DialogContent>
                        </Dialog>
                    </div>
                </div>
                <CardDescription>
                    Manage your own API keys for LLM providers (BYOK)
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Provider Status Overview */}
                <div className="flex flex-wrap gap-2 pb-4 border-b">
                    {providers.map((provider) => (
                        <Badge
                            key={provider.id}
                            variant="outline"
                            className={`${getProviderBadgeColor(provider)} transition-colors`}
                        >
                            {provider.name}
                            {provider.has_user_key && <Check className="w-3 h-3 ml-1" />}
                        </Badge>
                    ))}
                </div>

                {/* Key List */}
                {isLoading ? (
                    <div className="text-center py-8 text-muted-foreground">
                        Loading keys...
                    </div>
                ) : apiKeys.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                        <Key className="w-12 h-12 mx-auto mb-3 opacity-50" />
                        <p>No API keys configured</p>
                        <p className="text-sm mt-1">
                            Add your own keys to use different LLM providers
                        </p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {apiKeys.map((key) => (
                            <div
                                key={key.id}
                                className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${key.is_active
                                    ? "bg-card border-border"
                                    : "bg-muted/50 border-muted"
                                    }`}
                            >
                                <div className="flex items-center gap-3">
                                    <div
                                        className={`w-2 h-2 rounded-full ${key.is_active ? "bg-green-500" : "bg-gray-400"
                                            }`}
                                    />
                                    <div>
                                        <div className="font-medium flex items-center gap-2">
                                            {key.provider_name}
                                            <span className="text-muted-foreground font-mono text-sm">
                                                {key.display_suffix}
                                            </span>
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {key.label && <span>{key.label} · </span>}
                                            Added {formatDate(key.created_at)}
                                            {key.last_used_at && (
                                                <span> · Last used {formatDate(key.last_used_at)}</span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2">
                                    <Switch
                                        checked={key.is_active}
                                        onCheckedChange={() => handleToggleActive(key)}
                                    />
                                    <AlertDialog>
                                        <AlertDialogTrigger asChild>
                                            <Button variant="ghost" size="icon" className="text-destructive">
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </AlertDialogTrigger>
                                        <AlertDialogContent>
                                            <AlertDialogHeader>
                                                <AlertDialogTitle>Delete API Key?</AlertDialogTitle>
                                                <AlertDialogDescription>
                                                    This will permanently delete your {key.provider_name} API
                                                    key. You can add it again later if needed.
                                                </AlertDialogDescription>
                                            </AlertDialogHeader>
                                            <AlertDialogFooter>
                                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                                <AlertDialogAction
                                                    onClick={() => handleDeleteKey(key)}
                                                    className="bg-destructive text-destructive-foreground"
                                                >
                                                    Delete
                                                </AlertDialogAction>
                                            </AlertDialogFooter>
                                        </AlertDialogContent>
                                    </AlertDialog>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Info */}
                <div className="text-xs text-muted-foreground pt-4 border-t">
                    <p>Add your API keys to use LLM providers. Keys are encrypted and stored securely.</p>
                </div>
            </CardContent>
        </Card>
    );
}
