document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const messageDiv = document.getElementById("message");
  const signupContainer = document.getElementById("signup-container");
  const userMenuToggle = document.getElementById("user-menu-toggle");
  const authMenu = document.getElementById("auth-menu");
  const authStatus = document.getElementById("auth-status");
  const loginOpen = document.getElementById("login-open");
  const logoutButton = document.getElementById("logout-button");
  const loginDialog = document.getElementById("login-dialog");
  const loginForm = document.getElementById("login-form");
  const loginError = document.getElementById("login-error");
  let isAuthenticated = false;

  function showMessage(message, type) {
    messageDiv.textContent = message;
    messageDiv.className = type;
    messageDiv.classList.remove("hidden");
    setTimeout(() => messageDiv.classList.add("hidden"), 5000);
  }

  function updateAuthState(authenticated, username = "") {
    isAuthenticated = authenticated;
    signupContainer.classList.toggle("hidden", !authenticated);
    authStatus.textContent = authenticated
      ? `Signed in as ${username}`
      : "Not signed in";
    loginOpen.classList.toggle("hidden", authenticated);
    logoutButton.classList.toggle("hidden", !authenticated);
  }

  async function fetchAuthStatus() {
    const response = await fetch("/auth/status");
    if (!response.ok) {
      throw new Error("Unable to check teacher login status");
    }
    const status = await response.json();
    updateAuthState(status.authenticated, status.username || "");
  }

  // Function to fetch activities from API
  async function fetchActivities() {
    try {
      const response = await fetch("/activities");
      const activities = await response.json();

      // Clear loading message
      activitiesList.innerHTML = "";
      activitySelect.querySelectorAll("option:not(:first-child)").forEach((option) => option.remove());

      // Populate activities list
      Object.entries(activities).forEach(([name, details]) => {
        const activityCard = document.createElement("div");
        activityCard.className = "activity-card";

        const spotsLeft =
          details.max_participants - details.participants.length;

        // Create participants HTML with delete icons instead of bullet points
        const participantsHTML =
          details.participants.length > 0
            ? `<div class="participants-section">
              <h5>Participants:</h5>
              <ul class="participants-list">
                ${details.participants
                  .map(
                  (email) => `<li>
                    <span class="participant-email">${email}</span>
                    ${isAuthenticated
                      ? `<button type="button" class="delete-btn" data-activity="${name}" data-email="${email}" aria-label="Unregister ${email} from ${name}">Remove</button>`
                      : ""}
                  </li>`
                )
                .join("")}
            </ul>
            </div>`
            : `<p><em>No participants yet</em></p>`;

        activityCard.innerHTML = `
          <h4>${name}</h4>
          <p>${details.description}</p>
          <p><strong>Schedule:</strong> ${details.schedule}</p>
          <p><strong>Availability:</strong> ${spotsLeft} spots left</p>
          <div class="participants-container">
            ${participantsHTML}
          </div>
        `;

        activitiesList.appendChild(activityCard);

        // Add option to select dropdown
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        activitySelect.appendChild(option);
      });

      // Add event listeners to delete buttons
      document.querySelectorAll(".delete-btn").forEach((button) => {
        button.addEventListener("click", handleUnregister);
      });
    } catch (error) {
      activitiesList.innerHTML =
        "<p>Failed to load activities. Please try again later.</p>";
      console.error("Error fetching activities:", error);
    }
  }

  // Handle unregister functionality
  async function handleUnregister(event) {
    const button = event.currentTarget;
    const activity = button.getAttribute("data-activity");
    const email = button.getAttribute("data-email");

    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(
          activity
        )}/unregister?email=${encodeURIComponent(email)}`,
        {
          method: "DELETE",
        }
      );

      const result = await response.json();

      if (response.ok) {
        showMessage(result.message, "success");
        // Refresh activities list to show updated participants
        fetchActivities();
      } else {
        showMessage(result.detail || "An error occurred", "error");
      }
    } catch (error) {
      showMessage("Failed to unregister. Please try again.", "error");
      console.error("Error unregistering:", error);
    }
  }

  userMenuToggle.addEventListener("click", () => {
    const isExpanded = userMenuToggle.getAttribute("aria-expanded") === "true";
    userMenuToggle.setAttribute("aria-expanded", String(!isExpanded));
    authMenu.classList.toggle("hidden", isExpanded);
  });

  loginOpen.addEventListener("click", () => {
    loginError.classList.add("hidden");
    loginForm.reset();
    loginDialog.showModal();
  });

  document.getElementById("login-cancel").addEventListener("click", () => {
    loginDialog.close();
  });

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginError.classList.add("hidden");

    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: document.getElementById("username").value,
          password: document.getElementById("password").value,
        }),
      });
      const result = await response.json();

      if (!response.ok) {
        loginError.textContent = result.detail || "Unable to log in";
        loginError.classList.remove("hidden");
        return;
      }

      updateAuthState(true, result.username);
      loginDialog.close();
      loginForm.reset();
      authMenu.classList.add("hidden");
      userMenuToggle.setAttribute("aria-expanded", "false");
      showMessage("Teacher signed in", "success");
      await fetchActivities();
    } catch (error) {
      loginError.textContent = "Unable to log in. Please try again.";
      loginError.classList.remove("hidden");
      console.error("Error signing in:", error);
    }
  });

  logoutButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/auth/logout", { method: "POST" });
      if (!response.ok) {
        throw new Error("Logout request failed");
      }
      updateAuthState(false);
      authMenu.classList.add("hidden");
      userMenuToggle.setAttribute("aria-expanded", "false");
      showMessage("Teacher signed out", "success");
      await fetchActivities();
    } catch (error) {
      showMessage("Unable to log out. Please try again.", "error");
      console.error("Error signing out:", error);
    }
  });

  // Handle form submission
  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const email = document.getElementById("email").value;
    const activity = document.getElementById("activity").value;

    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(
          activity
        )}/signup?email=${encodeURIComponent(email)}`,
        {
          method: "POST",
        }
      );

      const result = await response.json();

      if (response.ok) {
        showMessage(result.message, "success");
        signupForm.reset();

        // Refresh activities list to show updated participants
        fetchActivities();
      } else {
        showMessage(result.detail || "An error occurred", "error");
      }
    } catch (error) {
      showMessage("Failed to sign up. Please try again.", "error");
      console.error("Error signing up:", error);
    }
  });

  async function initialize() {
    try {
      await fetchAuthStatus();
    } catch (error) {
      updateAuthState(false);
      showMessage("Unable to check teacher login status. Registration changes are disabled.", "error");
      console.error("Error initializing:", error);
    }
    await fetchActivities();
  }

  initialize();
});
