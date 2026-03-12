import { test, expect } from '@playwright/test';

test.describe('Chat', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
  });

  test('chat FAB button exists', async ({ page }) => {
    await expect(page.locator('#chat-fab')).toBeVisible();
  });

  test('click FAB, chat panel opens', async ({ page }) => {
    const chatPanel = page.locator('#chat-panel');
    await expect(chatPanel).not.toHaveClass(/open/);

    await page.locator('#chat-fab').click();
    await expect(chatPanel).toHaveClass(/open/);
  });

  test('type message and send, response bubble appears', async ({ page }) => {
    // Open chat panel
    await page.locator('#chat-fab').click();
    await expect(page.locator('#chat-panel')).toHaveClass(/open/);

    // Type a message and send
    const chatInput = page.locator('#chat-input');
    await chatInput.fill('What is the quietest borough in London?');
    await page.locator('#chat-send').click();

    // Wait for a bot response bubble (beyond the initial welcome message)
    // The welcome message is #chat-welcome; new bot replies are additional .chat-msg.bot elements
    const botMessages = page.locator('#chat-messages .chat-msg.bot');
    await expect(botMessages).toHaveCount(2, { timeout: 20_000 }); // welcome + response
  });
});
