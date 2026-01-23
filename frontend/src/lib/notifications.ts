
export const requestNotificationPermission = async (): Promise<boolean> => {
    if (!("Notification" in window)) {
        console.warn("This browser does not support desktop notification");
        return false;
    }

    if (Notification.permission === "granted") {
        return true;
    }

    if (Notification.permission !== "denied") {
        const permission = await Notification.requestPermission();
        return permission === "granted";
    }

    return false;
};

export const sendNotification = (title: string, body: string) => {
    if (Notification.permission === "granted") {
        const notification = new Notification(title, {
            body: body,
            icon: "/favicon.ico", // Ensure this path is correct for your project
            badge: "/favicon.ico"
        });

        notification.onclick = function () {
            window.focus();
            notification.close();
        };
    }
};
